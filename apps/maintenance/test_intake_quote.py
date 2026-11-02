"""LV-383 PR 2b: the workshop QUOTE as a document that finds or creates the intake.

Synthetic PDF and fictitious data only (OT `TEST-00002`, e-mails @example.test, RUT
11.111.111-1). A team may go straight to the workshop, so the first document can be
the quote; the reception then completes the same intake, in any order.
"""

import io
import logging
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from reportlab.pdfgen import canvas

from apps.core.pdf_text import text_from_pdf
from apps.maintenance.intake_readers import READERS, read_intake
from apps.maintenance.intake_readers.geocom_quote import (
    SUMMARY_LIMIT,
    GeocomQuoteReader,
)
from apps.maintenance.models import MaintenanceRecord, WorkshopIntake
from apps.maintenance.test_intake_readers import FULL_TEXT as RECEPTION_TEXT
from apps.maintenance.test_workshop_intake import _aircraft

FAKE_RUT = "11.111.111-1"
QUOTE_LINES = [
    "GEOCOM   COTIZACION DE SERVICIO TECNICO",
    "Santiago, 01/01/2026",
    "Atencion: Persona Contacto  (contacto@example.test)",
    f"Cliente: Empresa Ejemplo   RUT: {FAKE_RUT}",
    "OT: TEST-00002",
    "1.0 Identificacion",
    "Equipo: 00_DJI TEST   N DE SERIE TESTSERIAL00000002",
    "4.0 Resumen",
    "- Observaciones: se detecta juego en el gimbal y",
    "  conector de bateria con desgaste.",
    "- Horas de vuelo: 120",
    "- Numero de vuelos: 340",
    "- Ciclos de baterias: 85",
    "- Firmware: v00.00.0000",
    "- Mantencion recomendada: cambio de gimbal.",
    "5.0 Condiciones comerciales",
    "Neto $ 100.000",
    "IVA (19%) $ 19.000",
    "Total $ 119.000",
    "Validez de la Cotizacion: 10 dias",
    "Plazo de entrega: 15 dias habiles",
    "Garantia: 30 dias",
    f"Pago a Banco Ejemplo, cuenta corriente 000000000, RUT {FAKE_RUT}, "
    "pagos@example.test",
]
QUOTE_TEXT = "\n".join(QUOTE_LINES)


def make_pdf(lines):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 800
    for line in lines:
        pdf.drawString(40, y, line)
        y -= 16
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer


def _data(proposal, **extra):
    data = {
        "workshop_name": proposal.workshop_name,
        "workshop_order": proposal.workshop_order,
        "reader": proposal.reader,
    }
    for name in (
        "received_at",
        "delivered_by",
        "accessories",
        "findings",
        "quote_date",
        "quote_valid_until",
        "quote_net",
        "quote_vat",
        "quote_total",
        "quote_lead_time",
        "quote_warranty",
        "diagnosis",
    ):
        value = getattr(proposal, name, None)
        if value is not None:
            data[name] = value
    data.update(extra)
    return data


class TestQuoteReader:
    def test_complete_quote_from_a_real_pdf(self):
        text = text_from_pdf(make_pdf(QUOTE_LINES))
        proposal = read_intake(text)
        assert proposal is not None
        assert proposal.reader == "geocom_quote"
        assert proposal.workshop_name == "Geocom"
        assert proposal.workshop_order == "TEST-00002"
        assert proposal.serial_number == "TESTSERIAL00000002"
        assert proposal.equipment_label == "00_DJI TEST"
        assert proposal.quote_date == date(2026, 1, 1)
        assert proposal.quote_valid_until == date(2026, 1, 11)
        assert (proposal.quote_net, proposal.quote_vat, proposal.quote_total) == (
            100000,
            19000,
            119000,
        )
        assert proposal.quote_lead_time == "15 días hábiles"
        assert proposal.quote_warranty == "30 días"

    def test_the_summary_flattens_the_bullets(self):
        proposal = read_intake(QUOTE_TEXT)
        summary = proposal.diagnosis
        assert "\n" not in summary and "- " not in summary
        for expected in (
            "juego en el gimbal y conector de bateria con desgaste",
            "Horas de vuelo: 120",
            "Numero de vuelos: 340",
            "Ciclos de baterias: 85",
            "Firmware: v00.00.0000",
            "Mantencion recomendada: cambio de gimbal",
        ):
            assert expected in summary
        # The section after the summary is not part of it.
        assert "Neto" not in summary and "Condiciones" not in summary

    def test_a_long_summary_is_capped(self):
        long = QUOTE_TEXT.replace(
            "- Horas de vuelo: 120", "- Nota: " + "palabra " * 400
        )
        assert len(read_intake(long).diagnosis) <= SUMMARY_LIMIT + 1

    def test_broken_encoding_and_wrapped_lines_are_tolerated(self):
        text = (
            QUOTE_TEXT.replace("COTIZACION", "COTIZACI�N")
            .replace(
                "Validez de la Cotizacion: 10 dias",
                "Validez de la\nCotizaci�n: 10 d�as",
            )
            .replace(
                "Plazo de entrega: 15 dias habiles",
                "Plazo de\nentrega: 15 d�as h�biles",
            )
            .replace("Garantia: 30 dias", "Garant�a: 30 d�as")
            .replace("N DE SERIE", "N� DE\nSERIE")
            .replace("GEOCOM   COTIZACI", "GEOCOM\nCOTIZACI")
        )
        proposal = read_intake(text)
        assert proposal.reader == "geocom_quote"
        assert proposal.serial_number == "TESTSERIAL00000002"
        assert proposal.quote_valid_until == date(2026, 1, 11)
        assert proposal.quote_lead_time == "15 días hábiles"
        assert proposal.quote_warranty == "30 días"

    def test_commercial_proposal_title_is_also_recognized(self):
        text = QUOTE_TEXT.replace(
            "COTIZACION DE SERVICIO TECNICO", "PROPUESTA COMERCIAL"
        )
        assert read_intake(text).reader == "geocom_quote"

    def test_not_geocom_gives_none(self):
        assert read_intake(QUOTE_TEXT.replace("GEOCOM", "OTRO TALLER")) is None
        assert GeocomQuoteReader().matches("COTIZACION de otro taller") is False

    def test_a_reception_is_not_read_as_a_quote(self):
        assert GeocomQuoteReader().matches(RECEPTION_TEXT) is False
        assert read_intake(RECEPTION_TEXT).reader == "geocom"
        assert [r.name for r in READERS] == ["geocom", "geocom_quote"]

    def test_a_cut_document_leaves_the_rest_none_without_raising(self):
        proposal = read_intake("GEOCOM COTIZACION\nSantiago, 01/01/2026")
        assert proposal.quote_date == date(2026, 1, 1)
        assert proposal.quote_valid_until is None
        assert proposal.workshop_order is None and proposal.serial_number is None
        assert proposal.quote_total is None and proposal.diagnosis is None
        assert proposal.quote_lead_time is None and proposal.quote_warranty is None

    def test_an_impossible_date_gives_none(self):
        proposal = read_intake(QUOTE_TEXT.replace("01/01/2026", "31/02/2026"))
        assert proposal.quote_date is None and proposal.quote_valid_until is None

    @pytest.mark.parametrize(
        "net, vat, total",
        [
            ("100.000", "19.000", "119.000"),
            ("100,000", "19,000", "119,000"),
            ("100 000", "19 000", "119 000"),
            ("100000", "19000", "119000"),
        ],
    )
    def test_amounts_with_any_thousands_separator(self, net, vat, total):
        text = (
            QUOTE_TEXT.replace("$ 100.000", f"$ {net}")
            .replace("$ 19.000", f"$ {vat}")
            .replace("$ 119.000", f"$ {total}")
        )
        proposal = read_intake(text)
        assert (proposal.quote_net, proposal.quote_vat, proposal.quote_total) == (
            100000,
            19000,
            119000,
        )

    def test_the_order_is_normalized_like_the_reception_reader(self):
        text = QUOTE_TEXT.replace("OT: TEST-00002", "OT: CE - 71797")
        assert read_intake(text).workshop_order == "CE-71797"

    def test_the_serial_is_kept_as_read(self):
        text = QUOTE_TEXT.replace("TESTSERIAL00000002", "TESTSERIAL0O0000002")
        assert read_intake(text).serial_number == "TESTSERIAL0O0000002"

    def test_the_proposal_has_no_place_for_personal_or_bank_data(self):
        proposal = read_intake(QUOTE_TEXT)
        rendered = repr(proposal)
        for private in (FAKE_RUT, "example.test", "000000000", "Persona Contacto"):
            assert private not in rendered


@pytest.mark.django_db
class TestQuoteAndReceptionMerge:
    def _quote(self):
        return _data(read_intake(QUOTE_TEXT))

    def _reception(self):
        received = datetime(2026, 1, 3, 10, 0, tzinfo=ZoneInfo("America/Santiago"))
        return {
            "workshop_name": "Geocom",
            "workshop_order": "TEST-00002",
            "received_at": received,
            "delivered_by": "Persona Ejemplo",
            "accessories": "Control remoto",
            "findings": "Se recibe sin tapa de gimbal.",
            "reader": "geocom",
        }

    def test_a_quote_alone_creates_an_intake_without_received_at(self):
        aircraft = _aircraft()
        intake = MaintenanceRecord.register_workshop_intake(aircraft, self._quote())
        intake.refresh_from_db()
        assert intake.received_at is None
        assert intake.quote_total == Decimal("119000")
        assert intake.quote_lead_time == "15 días hábiles"
        assert "Horas de vuelo" in intake.diagnosis
        assert intake.record.status == "at_workshop"
        assert intake.record.description.startswith("Observaciones")

    def test_a_quote_over_an_existing_intake_completes_it_without_overwriting(self):
        aircraft = _aircraft()
        first = MaintenanceRecord.register_workshop_intake(aircraft, self._reception())
        quote = self._quote()
        quote["findings"] = "OTRO TEXTO QUE NO DEBE PISAR"
        quote["delivered_by"] = "Otra Persona"
        quote["received_at"] = timezone.now()

        second = MaintenanceRecord.register_workshop_intake(aircraft, quote)

        assert second.pk == first.pk
        assert WorkshopIntake.objects.count() == 1
        assert MaintenanceRecord.objects.filter(aircraft=aircraft).count() == 1
        second.refresh_from_db()
        assert second.findings == "Se recibe sin tapa de gimbal."
        assert second.delivered_by == "Persona Ejemplo"
        assert second.received_at == self._reception()["received_at"]
        assert second.quote_net == Decimal("100000")
        assert second.diagnosis.startswith("Observaciones")

    def test_a_reception_after_the_quote_fills_received_at(self):
        aircraft = _aircraft()
        first = MaintenanceRecord.register_workshop_intake(aircraft, self._quote())
        second = MaintenanceRecord.register_workshop_intake(aircraft, self._reception())
        assert second.pk == first.pk
        second.refresh_from_db()
        assert second.received_at == self._reception()["received_at"]
        assert second.delivered_by == "Persona Ejemplo"
        assert second.quote_total == Decimal("119000")

    @staticmethod
    def _snapshot(intake):
        intake.refresh_from_db()
        skip = {"id", "created_at", "updated_at", "record", "reader", "notes"}
        return {
            f.name: getattr(intake, f.attname)
            for f in intake._meta.concrete_fields
            if f.name not in skip
        }

    def test_the_two_documents_in_any_order_give_the_same_intake(self):
        other = {"workshop_order": "TEST-00003"}
        a = MaintenanceRecord.register_workshop_intake(
            _aircraft("CC-501"), self._quote()
        )
        MaintenanceRecord.register_workshop_intake(a.record.aircraft, self._reception())
        b = MaintenanceRecord.register_workshop_intake(
            _aircraft("CC-502"), {**self._reception(), **other}
        )
        MaintenanceRecord.register_workshop_intake(
            b.record.aircraft, {**self._quote(), **other}
        )
        first, second = self._snapshot(a), self._snapshot(b)
        assert first.pop("workshop_order") == "TEST-00002"
        assert second.pop("workshop_order") == "TEST-00003"
        assert first == second
        assert first["received_at"] is not None

    def test_the_same_order_on_another_aircraft_is_refused(self):
        from django.core.exceptions import ValidationError

        MaintenanceRecord.register_workshop_intake(_aircraft("CC-503"), self._quote())
        other = _aircraft("CC-504")
        with pytest.raises(ValidationError):
            MaintenanceRecord.register_workshop_intake(other, self._reception())
        assert not MaintenanceRecord.objects.filter(aircraft=other).exists()

    def test_no_private_data_ends_up_in_the_model_or_the_logs(self, caplog):
        with caplog.at_level(logging.DEBUG):
            intake = MaintenanceRecord.register_workshop_intake(
                _aircraft("CC-505"), self._quote()
            )
        values = " ".join(
            str(getattr(intake, f.attname) or "") for f in intake._meta.concrete_fields
        )
        for private in (FAKE_RUT, "example.test", "000000000", "Persona Contacto"):
            assert private not in values
            assert private not in caplog.text
