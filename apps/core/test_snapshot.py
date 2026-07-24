import json

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command

from apps.compliance.models import Document, DocumentType
from apps.core.anonymized_snapshot import get_snapshot_models
from apps.registry.models import Aircraft, CostCenter, Operator


@pytest.mark.django_db
def test_anonymized_snapshot_round_trip(tmp_path, settings):
    settings.DOCUMENTS_STORAGE_BACKEND = "local"
    settings.DOCUMENTS_ROOT = tmp_path / "documents"
    center = CostCenter.objects.create(code="CC-REAL", name="Private unit", responsible="Real person")
    aircraft = Aircraft.objects.create(
        registration="CC-REAL-1",
        type="RPA",
        model="Private model",
        manufacturer="Private manufacturer",
        cost_center=center,
    )
    Operator.objects.create(
        employee_id="REAL-1",
        full_name="Real person",
        email="real.person@example.org",
        phone="+56955555555",
        rut="12.345.678-9",
        address="Private address",
        cost_center=center,
    )
    doc_type = DocumentType.objects.create(code="CERT", name="Certificate")
    Document.objects.create(
        content_type=ContentType.objects.get_for_model(aircraft),
        object_id=aircraft.pk,
        doc_type=doc_type,
        title="Private certificate",
        file_path="",
        issue_date="2025-01-01",
    )

    snapshot = tmp_path / "snapshot.json"
    call_command("export_anonymized_snapshot", str(snapshot))
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    operator_rows = payload["models"]["registry.Operator"]
    assert operator_rows[0]["full_name"].startswith("Datos de prueba")
    assert "real.person@example.org" not in snapshot.read_text(encoding="utf-8")
    assert payload["models"]["compliance.Document"][0]["file_path"] == ""

    for _label, model in reversed(get_snapshot_models()):
        model.objects.all().delete()

    call_command("import_anonymized_snapshot", str(snapshot))

    imported_operator = Operator.objects.get()
    imported_document = Document.objects.get()
    assert imported_operator.email == "operator-0001@example.test"
    assert imported_operator.rut == "TEST-0001"
    assert str(imported_document.object_id) == str(Aircraft.objects.get().pk)
    assert imported_document.file_path.startswith("synthetic/document/")
    assert (settings.DOCUMENTS_ROOT / imported_document.file_path).is_file()
