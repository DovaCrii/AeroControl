from datetime import date

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import ProtectedError
from django.test import Client
from django.urls import reverse

from apps.core.models import AuditEvent

from apps.compliance import storage as storage_module
from apps.compliance.storage import (
    DocumentStorageError,
    DocumentStorageNotFound,
    LocalDocumentStorage,
    S3DocumentStorage,
    get_document_storage,
)
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule, Document, DocumentType
from apps.registry.models import Aircraft, CostCenter


@pytest.mark.django_db
def test_document_content_type_cannot_be_deleted_while_referenced():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    doc_type = DocumentType.objects.create(code="cert", name="Certificate")
    aircraft_type = ContentType.objects.get_for_model(Aircraft)
    Document.objects.create(
        title="Cert",
        doc_type=doc_type,
        content_type=aircraft_type,
        object_id=aircraft.pk,
        file_path="cert/aircraft/file.pdf",
        issue_date=date(2026, 1, 1),
    )

    with pytest.raises(ProtectedError):
        aircraft_type.delete()


@pytest.mark.django_db
def test_document_replace_is_audited_with_replaced_document_id(settings, tmp_path):
    settings.DOCUMENTS_ROOT = str(tmp_path)
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    doc_type = DocumentType.objects.create(
        code="cert", name="Certificate", requires_expiry=False
    )
    aircraft_type = ContentType.objects.get_for_model(Aircraft)
    old = Document.objects.create(
        title="Cert",
        doc_type=doc_type,
        content_type=aircraft_type,
        object_id=aircraft.pk,
        file_path="cert/aircraft/old.pdf",
        issue_date=date(2026, 1, 1),
    )
    User.objects.create_superuser("admin", "admin@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")

    response = client.post(
        reverse("document-replace", args=[old.pk]),
        {
            "title": "Cert",
            "doc_type": doc_type.pk,
            "entity_type": aircraft_type.pk,
            "object_id": str(aircraft.pk),
            "issue_date": date(2026, 6, 1),
            "file": SimpleUploadedFile(
                "new.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"
            ),
        },
    )

    assert response.status_code == 302
    old.refresh_from_db()
    assert old.is_current_version is False
    new_document = Document.objects.get(is_current_version=True, object_id=aircraft.pk)
    event = AuditEvent.objects.latest("created_at")
    assert event.action == "document_replaced"
    assert event.model_label == "compliance.Document"
    assert event.object_id == str(new_document.pk)
    assert event.metadata["replaced_document_id"] == str(old.pk)


@pytest.mark.django_db
def test_alert_rule_cannot_be_deleted_while_it_has_alerts():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    rule = AlertRule.objects.create(
        name="Aircraft status", entity_type="aircraft", field_to_watch="status"
    )
    Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk,
        message="test alert",
    )

    with pytest.raises(ProtectedError):
        rule.delete()


@pytest.mark.django_db
def test_local_storage_round_trip(tmp_path, settings):
    settings.DOCUMENTS_STORAGE_BACKEND = "local"
    settings.DOCUMENTS_ROOT = tmp_path
    storage = get_document_storage()
    uploaded = SimpleUploadedFile("report.pdf", b"private test document")

    storage.save("insurance/aircraft/report.pdf", uploaded)

    assert storage.exists("insurance/aircraft/report.pdf")
    with storage.open("insurance/aircraft/report.pdf") as stream:
        assert stream.read() == b"private test document"
    storage.delete("insurance/aircraft/report.pdf")
    assert not storage.exists("insurance/aircraft/report.pdf")


def test_local_storage_rejects_traversal(tmp_path):
    storage = LocalDocumentStorage(tmp_path)

    with pytest.raises(DocumentStorageError):
        storage.save("../outside.txt", SimpleUploadedFile("x.txt", b"x"))


class FakeS3Client:
    def __init__(self):
        self.objects = {}

    def upload_fileobj(self, uploaded, bucket, key, ExtraArgs):
        self.objects[(bucket, key)] = (uploaded.read(), ExtraArgs["ContentType"])

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            error = storage_module.ClientError(
                {"Error": {"Code": "NoSuchKey"}}, "GetObject"
            )
            raise error
        content, _content_type = self.objects[(Bucket, Key)]
        from io import BytesIO

        return {"Body": BytesIO(content)}

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise storage_module.ClientError(
                {"Error": {"Code": "NotFound"}}, "HeadObject"
            )

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


def test_s3_storage_round_trip(monkeypatch, settings):
    client = FakeS3Client()
    monkeypatch.setattr(storage_module.boto3, "client", lambda *args, **kwargs: client)
    settings.DOCUMENTS_STORAGE_BACKEND = "s3"
    settings.DOCUMENTS_STORAGE_BUCKET = "private-documents"
    settings.DOCUMENTS_STORAGE_ENDPOINT_URL = "https://storage.example.test"
    settings.DOCUMENTS_STORAGE_REGION = "us-east-1"
    settings.DOCUMENTS_STORAGE_ACCESS_KEY = "access"
    settings.DOCUMENTS_STORAGE_SECRET_KEY = "secret"
    storage = S3DocumentStorage()

    uploaded = SimpleUploadedFile("report.pdf", b"remote test document")
    storage.save("documents/report.pdf", uploaded)

    with storage.open("documents/report.pdf") as stream:
        assert stream.read() == b"remote test document"
    assert storage.exists("documents/report.pdf")
    storage.delete("documents/report.pdf")
    assert not storage.exists("documents/report.pdf")


def test_s3_storage_missing_object(monkeypatch, settings):
    client = FakeS3Client()
    monkeypatch.setattr(storage_module.boto3, "client", lambda *args, **kwargs: client)
    settings.DOCUMENTS_STORAGE_BACKEND = "s3"
    settings.DOCUMENTS_STORAGE_BUCKET = "private-documents"
    storage = S3DocumentStorage()

    with pytest.raises(DocumentStorageNotFound):
        storage.open("documents/missing.pdf")


class TestFlightAreaAttachments:
    """KMZ flight areas and permission letters attach to the flight permission.

    Document is generic, so the permission was already a valid target; only the
    KMZ extension was missing from the upload whitelist.
    """

    @staticmethod
    def _permission(db):
        from apps.registry.models import Aircraft, CostCenter, Operator
        from apps.operations.models import FlightPermission

        center = CostCenter.objects.create(code="KMZ", name="Area tests")
        operator = Operator.objects.create(
            employee_id="KMZ-1", full_name="Pilot", cost_center=center
        )
        aircraft = Aircraft.objects.create(
            registration="CC-KMZ",
            type="Multirotor",
            model="M1",
            manufacturer="Maker",
            cost_center=center,
        )
        permission = FlightPermission.objects.create(
            permission_number="PV-KMZ-1",
            cost_center=center,
            purpose="Survey",
            valid_from=timezone.localdate(),
            valid_until=timezone.localdate(),
            location="Antofagasta",
        )
        permission.operators.add(operator)
        permission.aircraft_fleet.add(aircraft)
        return permission

    def _form_for(self, permission, upload):
        from django.contrib.contenttypes.models import ContentType
        from apps.compliance.forms import DocumentForm
        from apps.operations.models import FlightPermission

        # A flight area does not expire on its own; the permission it belongs
        # to carries the dates.
        doc_type = DocumentType.objects.create(
            code="area", name="Flight area", requires_expiry=False
        )
        return DocumentForm(
            data={
                "title": "Area de vuelo",
                "doc_type": doc_type.pk,
                "entity_type": ContentType.objects.get_for_model(FlightPermission).pk,
                "object_id": permission.pk,
                "issue_date": date(2026, 1, 1),
            },
            files={"file": upload},
        )

    @pytest.mark.django_db
    def test_kmz_attaches_to_a_flight_permission(self, db):
        permission = self._permission(db)
        # A KMZ is a ZIP, so it opens with the ZIP magic bytes.
        upload = SimpleUploadedFile(
            "area.kmz",
            b"PK\x03\x04" + b"\x00" * 40,
            content_type="application/vnd.google-earth.kmz",
        )

        form = self._form_for(permission, upload)

        assert form.is_valid(), form.errors

    @pytest.mark.django_db
    def test_plain_kml_is_accepted_too(self, db):
        permission = self._permission(db)
        upload = SimpleUploadedFile(
            "area.kml",
            b'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"/>',
            content_type="application/vnd.google-earth.kml+xml",
        )

        form = self._form_for(permission, upload)

        assert form.is_valid(), form.errors

    @pytest.mark.django_db
    def test_a_kmz_that_is_not_a_zip_is_rejected(self, db):
        permission = self._permission(db)
        upload = SimpleUploadedFile(
            "fake.kmz", b"just text", content_type="application/vnd.google-earth.kmz"
        )

        form = self._form_for(permission, upload)

        assert not form.is_valid()
        assert "file" in form.errors

    @pytest.mark.django_db
    def test_an_unlisted_extension_is_still_rejected(self, db):
        permission = self._permission(db)
        upload = SimpleUploadedFile(
            "script.exe", b"MZ\x90\x00", content_type="application/x-msdownload"
        )

        form = self._form_for(permission, upload)

        assert not form.is_valid()
        assert "file" in form.errors
