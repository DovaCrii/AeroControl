"""R4.1 end-to-end: import_document_repository walks a real (temporary) tree
and talks to a real (test) database. The classification rules themselves are
covered filesystem-free in test_r4_repository_import.py -- this file checks
the wiring: report vs --apply, idempotency, and the blocking rule."""

import io
import shutil

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.compliance.models import Document, DocumentType
from apps.registry.models import Aircraft, CostCenter


def _build_tree(root):
    matched = root / "CC1-SER1-M3E"
    (matched / "01.- Documentos registro DGAC").mkdir(parents=True)
    (matched / "01.- Documentos registro DGAC" / "cert.pdf").write_bytes(b"cert-bytes")
    (matched / "01.- Documentos registro DGAC" / "Cedula de identidad.pdf").write_bytes(
        b"pii-bytes"
    )
    (matched / "05.- Seguro a terceros").mkdir()
    (matched / "05.- Seguro a terceros" / "poliza.pdf").write_bytes(b"policy-bytes")
    (matched / "05.- Seguro a terceros" / "backup.rar").write_bytes(b"rar-bytes")

    orphan = root / "CC2-UNKNOWNSERIAL-M4E"
    (orphan / "01.- Documentos registro DGAC").mkdir(parents=True)
    (orphan / "01.- Documentos registro DGAC" / "doc.pdf").write_bytes(b"orphan-bytes")

    excluded = root / "DOCUMENTOS BASES"
    excluded.mkdir()
    (excluded / "AOC.pdf").write_bytes(b"aoc-bytes")

    # Real production has one subfolder with its own nested subfolder
    # ("02.- Solicitud de Vuelos/Junio-Agosto/").
    nested = matched / "02.- Solicitud de Vuelos" / "Junio-Agosto"
    nested.mkdir(parents=True)
    (nested / "nested.pdf").write_bytes(b"nested-bytes")

    # Real production also has one file loose at an aircraft folder's own
    # root, outside any of the 5 numbered subfolders.
    loose_file = matched / "loose_manual.pdf"
    loose_file.write_bytes(b"loose-bytes")

    return matched, orphan, loose_file


@pytest.fixture
def seeded_doc_types(db):
    DocumentType.objects.create(code="aircraft-registration", name="Registro")
    DocumentType.objects.create(code="liability-insurance", name="Seguro")
    DocumentType.objects.create(code="flight-request", name="Solicitud de vuelo")


@pytest.fixture
def matched_aircraft(db):
    cost_center = CostCenter.objects.create(code="CC1")
    return Aircraft.objects.create(
        registration="RPA-1",
        type="Multirotor",
        model="M3E",
        manufacturer="DJI",
        serial_number="SER1",
        cost_center=cost_center,
    )


def _run(source, apply=False):
    out = io.StringIO()
    call_command(
        "import_document_repository",
        f"--source={source}",
        *(["--apply"] if apply else []),
        stdout=out,
    )
    return out.getvalue()


@pytest.mark.django_db
def test_report_mode_classifies_every_case_without_writing(
    tmp_path, seeded_doc_types, matched_aircraft
):
    _build_tree(tmp_path)

    output = _run(tmp_path, apply=False)

    assert "cert.pdf -- Listo para importar" in output
    assert "Cedula de identidad.pdf" in output and "REVIEW-SENSITIVE" in output
    assert "backup.rar" in output and "SKIP-FORMAT" in output
    assert "doc.pdf" in output and "REVIEW-NO-MATCH" in output
    assert "AOC.pdf" not in output  # DOCUMENTOS BASES is out of scope (R4.6)
    # A file inside a nested subfolder ("Junio-Agosto/") must still show up
    # in the report, with the nesting preserved in its path -- not silently
    # dropped, and not flattened into the parent subfolder's path.
    assert "Junio-Agosto/nested.pdf -- Listo para importar" in output
    # A file loose at the aircraft folder's own root has no filing
    # convention to guess -- it must be reported, not silently dropped.
    assert "loose_manual.pdf" in output and "REVIEW-UNKNOWN-SUBFOLDER" in output
    assert Document.objects.count() == 0


@pytest.mark.django_db
def test_apply_refuses_while_a_folder_has_no_aircraft_match(
    tmp_path, seeded_doc_types, matched_aircraft
):
    _build_tree(tmp_path)

    with pytest.raises(Exception, match="decisión humana"):
        _run(tmp_path, apply=True)

    assert Document.objects.count() == 0


@pytest.mark.django_db
def test_apply_imports_the_matched_aircraft_when_the_orphan_folder_is_removed(
    tmp_path, seeded_doc_types, matched_aircraft, settings
):
    settings.DOCUMENTS_ROOT = str(tmp_path / "storage")
    matched, orphan, loose_file = _build_tree(tmp_path / "source")
    shutil.rmtree(orphan)
    loose_file.unlink()

    _run(tmp_path / "source", apply=True)

    # cert.pdf + poliza.pdf + the nested Junio-Agosto/nested.pdf; PII/rar
    # skipped.
    assert Document.objects.count() == 3
    cert = Document.objects.get(source_reference__endswith="cert.pdf")
    assert cert.object_id == matched_aircraft.pk
    assert cert.doc_type.code == "aircraft-registration"
    assert cert.issue_date == timezone.localdate()
    assert len(cert.content_sha256) == 64
    policy = Document.objects.get(source_reference__endswith="poliza.pdf")
    assert policy.doc_type.code == "liability-insurance"
    nested = Document.objects.get(source_reference__endswith="nested.pdf")
    assert nested.doc_type.code == "flight-request"
    assert "Junio-Agosto" in nested.source_reference


@pytest.mark.django_db
def test_apply_is_idempotent_on_a_second_run(
    tmp_path, seeded_doc_types, matched_aircraft, settings
):
    settings.DOCUMENTS_ROOT = str(tmp_path / "storage")
    matched, orphan, loose_file = _build_tree(tmp_path / "source")
    shutil.rmtree(orphan)
    loose_file.unlink()

    _run(tmp_path / "source", apply=True)
    assert Document.objects.count() == 3

    second_output = _run(tmp_path / "source", apply=True)

    assert Document.objects.count() == 3
    assert "ALREADY-IMPORTED" in second_output


@pytest.mark.django_db
def test_msg_file_blocks_apply_when_antivirus_is_not_configured(
    tmp_path, seeded_doc_types, matched_aircraft, settings
):
    settings.DOCUMENTS_ANTIVIRUS_COMMAND = ""
    matched = tmp_path / "CC1-SER1-M3E" / "01.- Documentos registro DGAC"
    matched.mkdir(parents=True)
    (matched / "trace.msg").write_bytes(b"msg-bytes")

    output = _run(tmp_path, apply=False)
    assert "REVIEW-NEEDS-ANTIVIRUS" in output

    with pytest.raises(Exception, match="decisión humana"):
        _run(tmp_path, apply=True)


@pytest.mark.django_db
def test_msg_file_is_imported_when_antivirus_scan_passes(
    tmp_path, seeded_doc_types, matched_aircraft, settings, monkeypatch
):
    settings.DOCUMENTS_ANTIVIRUS_COMMAND = "clamdscan"
    settings.DOCUMENTS_ROOT = str(tmp_path / "storage")
    monkeypatch.setattr(
        "apps.compliance.management.commands.import_document_repository."
        "scan_uploaded_file",
        lambda upload: None,
    )
    matched = tmp_path / "source" / "CC1-SER1-M3E" / "01.- Documentos registro DGAC"
    matched.mkdir(parents=True)
    (matched / "trace.msg").write_bytes(b"msg-bytes")

    _run(tmp_path / "source", apply=True)

    document = Document.objects.get(source_reference__endswith="trace.msg")
    assert document.doc_type.code == "aircraft-registration"


@pytest.mark.django_db
def test_msg_file_blocks_apply_when_antivirus_rejects_it(
    tmp_path, seeded_doc_types, matched_aircraft, settings, monkeypatch
):
    settings.DOCUMENTS_ANTIVIRUS_COMMAND = "clamdscan"

    def _reject(upload):
        raise RuntimeError("Antivirus scan rejected the uploaded file")

    monkeypatch.setattr(
        "apps.compliance.management.commands.import_document_repository."
        "scan_uploaded_file",
        _reject,
    )
    matched = tmp_path / "CC1-SER1-M3E" / "01.- Documentos registro DGAC"
    matched.mkdir(parents=True)
    (matched / "trace.msg").write_bytes(b"msg-bytes")

    with pytest.raises(Exception, match="decisión humana"):
        _run(tmp_path, apply=True)

    assert Document.objects.count() == 0
