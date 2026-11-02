"""LV-383 PR 2: workshop reception readers (synthetic, fictitious data only)."""

import io
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from reportlab.pdfgen import canvas

from apps.core.pdf_text import text_from_pdf
from apps.maintenance.intake_readers import READERS, IntakeProposal, read_intake
from apps.maintenance.intake_readers.geocom import GeocomReader
from apps.maintenance.intake_readers.geocom_quote import GeocomQuoteReader

FAKE_RUT = "11.111.111-1"
PAGE_1 = [
    "DOCUMENTO DE RECEPCION DE EQUIPOS",
    "Fecha: 01/01/2026",
    "Para consultas escriba a serviciotecnico@example.test (Geocom)",
    "CLIENTE: Empresa Ejemplo   RUT: 11.111.111-1   CONTACTO: Persona Contacto",
    "ENTREGADOS POR:",
    "Persona Ejemplo",
    FAKE_RUT,
    "II.- EQUIPOS RECEPCIONADOS",
    "N   OT   EQUIPO   SERIE",
    "1  TEST-00001  00_DJI TEST  TESTSERIAL00000001",
    "Fecha: 01/01/2026 10:00:00 (UTC-03:00:00)",
]
PAGE_2 = [
    "ESTADO DE SU OT",
    "1. INFORMACION DEL INSTRUMENTO:",
    "OT CLIENTE - N 00001",
    "EQUIPO 00_DJI TEST",
    "N DE SERIE TESTSERIAL00000001",
    "ACCESORIOS Control remoto, dos",
    "baterias y estuche",
    "2. OBSERVACIONES:",
    "Se recibe con helice danada",
    "y sin tapa de gimbal.",
]
FULL_TEXT = "\n".join(PAGE_1 + PAGE_2)


def make_pdf(pages):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for lines in pages:
        y = 800
        for line in lines:
            pdf.drawString(40, y, line)
            y -= 18
        pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer


def test_complete_document_fills_every_field():
    proposal = read_intake(FULL_TEXT)
    assert isinstance(proposal, IntakeProposal)
    assert proposal.reader == "geocom"
    assert proposal.workshop_name == "Geocom"
    assert proposal.workshop_order == "TEST-00001"
    assert proposal.serial_number == "TESTSERIAL00000001"
    assert proposal.equipment_label == "00_DJI TEST"
    assert proposal.accessories == "Control remoto, dos baterias y estuche"
    assert proposal.findings == "Se recibe con helice danada y sin tapa de gimbal."
    assert proposal.delivered_by == "Persona Ejemplo"
    assert proposal.received_at == datetime(
        2026, 1, 1, 10, 0, 0, tzinfo=ZoneInfo("America/Santiago")
    )


def test_order_keeps_the_workshop_format():
    text = FULL_TEXT.replace("TEST-00001", "CE-71876")
    assert read_intake(text).workshop_order == "CE-71876"


def test_broken_encoding_and_wrapped_lines_are_tolerated():
    text = (
        FULL_TEXT.replace("RECEPCION", "RECEPCI�N")
        .replace("INFORMACION", "INFORMACI�N")
        .replace("N DE SERIE", "N� DE\nSERIE")
        .replace("helice danada", "h�lice\nda�ada")
        .replace("DOCUMENTO DE", "DOCUMENTO\nDE")
    )
    proposal = read_intake(text)
    assert proposal is not None
    assert proposal.serial_number == "TESTSERIAL00000001"
    assert proposal.workshop_order == "TEST-00001"
    assert proposal.findings.startswith("Se recibe con h")
    assert proposal.delivered_by == "Persona Ejemplo"


def test_accented_title_matches():
    assert GeocomReader().matches("Documento de Recepción de Equipos GEOCOM")


def test_other_workshop_is_not_matched():
    text = "ORDEN DE TRABAJO\nTaller Otro\nSerie ABC123\n"
    assert GeocomReader().matches(text) is False
    assert read_intake(text) is None
    assert read_intake("DOCUMENTO DE RECEPCION DE EQUIPOS de otro taller") is None


def test_truncated_document_leaves_missing_fields_none():
    text = "\n".join(PAGE_1[:3] + PAGE_1[4:7])
    proposal = read_intake(text)
    assert proposal is not None
    assert proposal.delivered_by == "Persona Ejemplo"
    for field in (
        "workshop_order",
        "received_at",
        "serial_number",
        "equipment_label",
        "accessories",
        "findings",
    ):
        assert getattr(proposal, field) is None


def test_missing_observations_keeps_instrument_fields():
    text = "\n".join(PAGE_1 + PAGE_2[:5])
    proposal = read_intake(text)
    assert proposal.serial_number == "TESTSERIAL00000001"
    assert proposal.findings is None


@pytest.mark.parametrize("value", [None, "", "   \n", 123, b"bytes"])
def test_empty_or_non_text_gives_none(value):
    assert read_intake(value) is None


def test_invalid_date_is_none_not_an_error():
    text = FULL_TEXT.replace("01/01/2026 10:00:00", "31/02/2026 10:00:00")
    assert read_intake(text).received_at is None


def test_serial_is_returned_as_read():
    text = FULL_TEXT.replace("TESTSERIAL00000001", "TESTSERIALO0000001")
    assert read_intake(text).serial_number == "TESTSERIALO0000001"


def test_delivery_rut_is_never_kept():
    dump = repr(read_intake(FULL_TEXT))
    assert FAKE_RUT not in dump
    assert "11.111.111" not in dump
    assert "99.999.999" not in dump


def test_delivered_by_without_rut_takes_only_the_first_line():
    text = FULL_TEXT.replace(FAKE_RUT + "\n", "")
    assert read_intake(text).delivered_by == "Persona Ejemplo"


def test_registry_lists_the_geocom_readers():
    assert [type(reader) for reader in READERS] == [
        GeocomReader,
        GeocomQuoteReader,
    ]


def test_end_to_end_from_a_pdf():
    text = text_from_pdf(make_pdf([PAGE_1, PAGE_2]))
    proposal = read_intake(text)
    assert proposal is not None
    assert proposal.workshop_order == "TEST-00001"
    assert proposal.serial_number == "TESTSERIAL00000001"
    assert proposal.findings.endswith("sin tapa de gimbal.")
    assert FAKE_RUT not in repr(proposal)


def test_pdf_that_is_not_geocom_gives_none():
    text = text_from_pdf(make_pdf([["Factura 1", "Nada que ver"]]))
    assert read_intake(text) is None
