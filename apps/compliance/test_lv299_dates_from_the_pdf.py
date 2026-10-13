"""LV-299: subir la autorización de la DGAC saca las fechas del propio PDF.

Reporte del usuario (2026-10-13, con captura): *"yo puedo subir el permiso y eso saca las
fechas, pero no me lo permite al dar siguiente"*. Un permiso recién creado no tiene
fechas (la DGAC las entrega con la autorización), así que `LV-297` —que las tomaba del
permiso— dejaba el formulario atascado en «Este campo es obligatorio» justo al subir
el papel que las trae.
"""

import io
from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.compliance.forms import DocumentForm
from apps.compliance.models import DocumentType
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

RANGE = (
    "Rango de fecha autorizado para efectuar las siguientes operaciones : "
    "10/10/2026-10/01/2027"
)
OTHER_RANGE = RANGE.replace("10/10/2026", "01/11/2026").replace(
    "10/01/2027", "01/02/2027"
)


def _pdf(*lines):
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    for index, line in enumerate(lines):
        page.drawString(40, 750 - index * 20, line)
    page.save()
    return buffer.getvalue()


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC684", name="PMCHS", operates_flights=True)


@pytest.fixture
def bare_permit(centre):
    """Un permiso recién solicitado: todavía sin vigencia."""
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_REQUESTED,
        location="Calama",
        area_type="unpopulated",
    )


@pytest.fixture
def authorization(db):
    return DocumentType.objects.create(
        code="dgac-rpa-operation-authorization",
        name="Autorización",
        requires_expiry=True,
    )


def _form(permit, doc_type, pdf, **dates):
    data = {
        "entity_type": str(ContentType.objects.get_for_model(FlightPermission).pk),
        "object_id": str(permit.pk),
        "doc_type": str(doc_type.pk),
        **dates,
    }
    upload = SimpleUploadedFile("a.pdf", pdf, content_type="application/pdf")
    return DocumentForm(data=data, files={"file": upload}), upload


@pytest.mark.django_db
class TestDatesFromTheUploadedPdf:
    def test_a_permit_without_dates_gets_them_from_the_pdf(
        self, bare_permit, authorization
    ):
        form, _upload = _form(bare_permit, authorization, _pdf(RANGE))

        assert form.is_valid(), form.errors
        assert form.cleaned_data["issue_date"] == date(2026, 10, 10)
        assert form.cleaned_data["expiry_date"] == date(2027, 1, 10)

    def test_the_pdf_wins_over_the_permit_dates(self, bare_permit, authorization):
        bare_permit.valid_from = date(2026, 9, 1)
        bare_permit.valid_until = date(2026, 12, 1)
        bare_permit.save()

        form, _upload = _form(bare_permit, authorization, _pdf(RANGE))

        assert form.is_valid(), form.errors
        assert form.cleaned_data["issue_date"] == date(2026, 10, 10)

    def test_a_date_typed_by_hand_wins_over_the_pdf(self, bare_permit, authorization):
        form, _upload = _form(
            bare_permit,
            authorization,
            _pdf(RANGE),
            issue_date="2026-10-12",
            expiry_date="2027-01-05",
        )

        assert form.is_valid(), form.errors
        assert form.cleaned_data["issue_date"] == date(2026, 10, 12)
        assert form.cleaned_data["expiry_date"] == date(2027, 1, 5)

    def test_reading_the_pdf_leaves_the_file_intact_for_saving(
        self, bare_permit, authorization
    ):
        pdf = _pdf(RANGE)
        form, upload = _form(bare_permit, authorization, pdf)

        assert form.is_valid(), form.errors
        upload.seek(0)
        assert upload.read() == pdf

    def test_an_unreadable_pdf_falls_back_to_the_permit(
        self, bare_permit, authorization
    ):
        bare_permit.valid_from = date(2026, 9, 1)
        bare_permit.valid_until = date(2026, 12, 1)
        bare_permit.save()

        form, _upload = _form(bare_permit, authorization, b"%PDF-1.4\nnot really\n")

        assert form.is_valid(), form.errors
        assert form.cleaned_data["issue_date"] == date(2026, 9, 1)

    def test_unreadable_and_no_permit_dates_still_asks_for_them(
        self, bare_permit, authorization
    ):
        form, _upload = _form(bare_permit, authorization, b"%PDF-1.4\nnot really\n")

        assert not form.is_valid()
        assert "issue_date" in form.errors
        assert "expiry_date" in form.errors

    def test_two_different_ranges_are_not_guessed(self, bare_permit, authorization):
        form, _upload = _form(bare_permit, authorization, _pdf(RANGE, OTHER_RANGE))

        assert not form.is_valid()
        assert "issue_date" in form.errors

    def test_a_file_that_fails_validation_is_never_parsed(
        self, bare_permit, authorization, monkeypatch
    ):
        """Un `.pdf` cuya firma no es de PDF no llega al analizador."""
        calls = []
        monkeypatch.setattr(
            "apps.operations.dgac_pdf.window_from_pdf",
            lambda stream: calls.append(stream),
        )

        form, _upload = _form(bare_permit, authorization, b"MZ\x00\x00not a pdf")

        assert not form.is_valid()
        assert calls == []

    def test_only_the_authorization_type_reads_the_pdf(self, bare_permit, db):
        other = DocumentType.objects.create(
            code="other-type", name="Otro", requires_expiry=False
        )

        form, _upload = _form(bare_permit, other, _pdf(RANGE))

        assert not form.is_valid()
        assert "issue_date" in form.errors
