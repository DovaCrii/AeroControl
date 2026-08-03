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
def test_document_form_autogenerates_title_when_left_blank(settings, tmp_path):
    """LV-2: a blank title is filled in from doc_type + record + issue_date,
    instead of failing or saving an empty string that read differently
    session to session."""
    from apps.compliance.forms import DocumentForm

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

    form = DocumentForm(
        data={
            "title": "",
            "doc_type": doc_type.pk,
            "entity_type": aircraft_type.pk,
            "object_id": str(aircraft.pk),
            "issue_date": "2026-01-01",
        },
        files={
            "file": SimpleUploadedFile(
                "cert.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"
            )
        },
    )

    assert form.is_valid(), form.errors
    document = form.save()
    assert document.title == f"Certificate · {aircraft} · 2026-01-01"


@pytest.mark.django_db
def test_document_form_keeps_an_explicit_title(settings, tmp_path):
    from apps.compliance.forms import DocumentForm

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

    form = DocumentForm(
        data={
            "title": "My chosen title",
            "doc_type": doc_type.pk,
            "entity_type": aircraft_type.pk,
            "object_id": str(aircraft.pk),
            "issue_date": "2026-01-01",
        },
        files={
            "file": SimpleUploadedFile(
                "cert.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"
            )
        },
    )

    assert form.is_valid(), form.errors
    document = form.save()
    assert document.title == "My chosen title"


@pytest.mark.django_db
def test_document_form_saves_notes(settings, tmp_path):
    """LV-3: the notes field (already on BaseModel) is now reachable from the
    upload form instead of only from the technical admin."""
    from apps.compliance.forms import DocumentForm

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

    form = DocumentForm(
        data={
            "title": "Cert",
            "doc_type": doc_type.pk,
            "entity_type": aircraft_type.pk,
            "object_id": str(aircraft.pk),
            "issue_date": "2026-01-01",
            "notes": "Renewed early at the operator's request.",
        },
        files={
            "file": SimpleUploadedFile(
                "cert.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"
            )
        },
    )

    assert form.is_valid(), form.errors
    document = form.save()
    assert document.notes == "Renewed early at the operator's request."


@pytest.mark.django_db
def test_document_form_flags_the_empty_document_type_catalog():
    """LV-1: an empty catalog is explained instead of leaving a required,
    seemingly broken picker with no options."""
    from apps.compliance.forms import DocumentForm

    assert not DocumentType.objects.filter(is_active=True).exists()
    form = DocumentForm()
    help_text = str(form.fields["doc_type"].help_text)
    assert (
        "No document types configured yet" in help_text
        or "Aún no hay tipos de documento configurados" in help_text
    )


@pytest.mark.django_db
def test_seed_document_types_creates_catalog_including_one_insurance_type():
    """LV-1: the standard DGAC catalog seeds cleanly and idempotently."""
    from django.core.management import call_command

    call_command("seed_document_types")
    assert DocumentType.objects.count() == 9
    insurance_types = DocumentType.objects.filter(is_insurance=True)
    assert insurance_types.count() == 1
    assert insurance_types.first().code == "liability-insurance"
    # LV-30: the three per-flight operational-record types.
    op_records = DocumentType.objects.filter(is_operational_record=True)
    assert set(op_records.values_list("code", flat=True)) == {
        "flight-log",
        "rpa-checklist",
        "drone-inspection",
    }

    # Idempotent: a second run does not duplicate or touch existing rows.
    call_command("seed_document_types")
    assert DocumentType.objects.count() == 9


@pytest.mark.django_db
def test_seed_alert_rules_creates_the_two_essential_rules_idempotently():
    """The recommended rule set seeds cleanly, stays valid, and is idempotent."""
    from django.core.management import call_command

    call_command("seed_alert_rules")
    assert AlertRule.objects.count() == 2
    essential = AlertRule.objects.get(name="Documentos por vencer")
    assert essential.entity_type == "compliance.document"
    assert essential.field_to_watch == "expiry_date"
    assert essential.days_before_expiry == 30
    assert essential.enabled is True
    assert essential.create_kanban_task is False
    # Seeded rules must survive the model's own validation, or generate_alerts
    # would silently skip them every night.
    for rule in AlertRule.objects.all():
        rule.full_clean()

    # Idempotent: a second run does not duplicate.
    call_command("seed_alert_rules")
    assert AlertRule.objects.count() == 2


@pytest.mark.django_db
def test_seed_alert_rules_with_optional_adds_qualification_and_maintenance():
    from django.core.management import call_command

    call_command("seed_alert_rules", "--with-optional")
    assert AlertRule.objects.count() == 8
    assert AlertRule.objects.filter(
        entity_type="registry.qualification", field_to_watch="expiry_date"
    ).exists()
    assert AlertRule.objects.filter(
        entity_type="maintenance.maintenancerecord", field_to_watch="scheduled_date"
    ).exists()
    assert AlertRule.objects.filter(
        entity_type="maintenance.maintenancerecord", field_to_watch="status"
    ).exists()
    # LV-29: the two DGAC vigencia rules.
    assert AlertRule.objects.filter(
        entity_type="registry.operator", field_to_watch="credential_expiry"
    ).exists()
    assert AlertRule.objects.filter(
        entity_type="registry.aircraft", field_to_watch="insurance_expiry"
    ).exists()
    # LV-30: the monthly compliance review rule (watches status).
    assert AlertRule.objects.filter(
        entity_type="compliance.monthlycompliancereview", field_to_watch="status"
    ).exists()


@pytest.mark.django_db
def test_check_digest_recipients_classifies_reachable_and_missing():
    """The readiness report mirrors CostCenter.notification_email and explains
    why a cost center has no reachable digest recipient."""
    from apps.compliance.management.commands.check_digest_recipients import (
        recipient_status,
    )
    from apps.registry.models import Operator

    cc_operator = CostCenter.objects.create(code="CC1", name="Has operator")
    operator = Operator.objects.create(
        employee_id="E1", full_name="Ana", email="ana@x.cl", cost_center=cc_operator
    )
    cc_operator.responsible_operator = operator
    cc_operator.save()

    cc_contact = CostCenter.objects.create(
        code="CC2", name="Has contact", responsible_contact_email="c@x.cl"
    )
    cc_none = CostCenter.objects.create(code="CC3", name="Nobody")
    cc_no_email = CostCenter.objects.create(code="CC4", name="Operator without email")
    silent = Operator.objects.create(
        employee_id="E2", full_name="Beto", email="", cost_center=cc_no_email
    )
    cc_no_email.responsible_operator = silent
    cc_no_email.save()

    assert recipient_status(cc_operator)[0] is True
    assert "operator" in recipient_status(cc_operator)[2]
    assert recipient_status(cc_contact)[0] is True
    assert recipient_status(cc_none)[0] is False
    assert recipient_status(cc_no_email)[0] is False
    assert "no email" in recipient_status(cc_no_email)[2]


@pytest.mark.django_db
def test_check_digest_recipients_command_runs_and_summarises():
    from io import StringIO

    from django.core.management import call_command

    CostCenter.objects.create(code="CC1", name="X")
    out = StringIO()
    call_command("check_digest_recipients", stdout=out)
    text = out.getvalue()
    assert "cost centers" in text
    assert "missing a recipient" in text


@pytest.mark.django_db
def test_aircraft_and_operator_details_offer_a_documents_upload(admin_client):
    from django.contrib.contenttypes.models import ContentType

    from apps.registry.models import Operator

    cost_center = CostCenter.objects.create(code="CC1", name="One")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA", type="RPA", model="M3",
        manufacturer="DJI", cost_center=cost_center,
    )
    operator = Operator.objects.create(
        employee_id="E1", full_name="Ana", cost_center=cost_center
    )

    aircraft_ct = ContentType.objects.get_for_model(Aircraft)
    response = admin_client.get(reverse("aircraft-detail", args=[aircraft.pk]))
    content = response.content.decode()
    assert reverse("document-create") in content
    assert f"entity_type={aircraft_ct.pk}" in content
    assert f"object_id={aircraft.pk}" in content

    response = admin_client.get(reverse("operator-detail", args=[operator.pk]))
    assert reverse("document-create") in response.content.decode()


def test_cost_center_and_company_are_documentable():
    from apps.compliance.forms import DOCUMENTABLE_MODELS

    assert ("registry", "costcenter") in DOCUMENTABLE_MODELS
    assert ("core", "operationaltenant") in DOCUMENTABLE_MODELS


@pytest.mark.django_db
def test_company_documents_page_lists_tenant_docs_and_offers_upload(admin_client):
    from django.contrib.contenttypes.models import ContentType

    from apps.core.models import OperationalTenant
    from apps.core.tenancy import get_default_tenant

    tenant = OperationalTenant.objects.get(pk=get_default_tenant())
    doc_type = DocumentType.objects.create(code="aoc", name="AOC")
    Document.objects.create(
        title="AOC 1485",
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(OperationalTenant),
        object_id=tenant.pk,
        file_path="aoc.pdf",
        issue_date=date(2026, 1, 1),
    )

    response = admin_client.get(reverse("company-documents"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "AOC 1485" in content
    assert reverse("document-create") in content


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
