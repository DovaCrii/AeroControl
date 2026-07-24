from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import ProtectedError

from apps.compliance import storage as storage_module
from apps.compliance.storage import (
    DocumentStorageError,
    DocumentStorageNotFound,
    LocalDocumentStorage,
    S3DocumentStorage,
    get_document_storage,
)
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
