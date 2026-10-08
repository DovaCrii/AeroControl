"""LV-295: aprobar cruza la vigencia del permiso con la del PDF de la DGAC.

Pedido del usuario (2026-10-08, con la autorización a la vista): *"la vigencia del
permiso te la entrega el PDF […] debe ser ahí cruzado para aprobar"*, y *"al editar un
permiso y darle guardar no completa la acción y vuelve al inicio"*.
"""

import io
from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.compliance.storage import get_document_storage
from apps.core.testing import login_as
from apps.registry.models import CostCenter

from .dgac_pdf import window_from_pdf, window_from_text
from .models import FlightPermission

AUTHORIZATION = "dgac-rpa-operation-authorization"
RANGE = (
    "Rango de fecha autorizado para efectuar las siguientes operaciones : "
    "10/10/2026-10/01/2027"
)


def _pdf(*lines):
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    for index, line in enumerate(lines):
        page.drawString(40, 750 - index * 20, line)
    page.save()
    return buffer.getvalue()


def _permit(*lines, **extra):
    centre = CostCenter.objects.create(code="CC1", name="Uno", operates_flights=True)
    permit = FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_REQUESTED,
        permission_number="7218",
        location="Calama",
        area_type="unpopulated",
        **extra,
    )
    doc_type, _created = DocumentType.objects.get_or_create(
        code=AUTHORIZATION, defaults={"name": AUTHORIZATION}
    )
    path = f"test/{permit.pk}.pdf"
    get_document_storage().save(
        path, ContentFile(_pdf(*lines) if lines else b"not a pdf")
    )
    Document.objects.create(
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permit.pk,
        doc_type=doc_type,
        title="Autorizacion",
        file_path=path,
        issue_date="2026-10-01",
    )
    return permit


def _approve(permit):
    client = login_as("view_flightpermission", "change_flightpermission")
    return client.post(reverse("permission-approve", args=[permit.pk]), follow=True)


class TestReadingTheWindow:
    def test_the_text_of_the_real_authorization(self):
        assert window_from_text(RANGE) == (date(2026, 10, 10), date(2027, 1, 10))

    def test_it_reads_a_real_pdf(self):
        assert window_from_pdf(io.BytesIO(_pdf(RANGE))) == (
            date(2026, 10, 10),
            date(2027, 1, 10),
        )

    def test_two_different_ranges_give_no_answer(self):
        text = RANGE + "\n" + RANGE.replace("10/01/2027", "10/02/2027")

        assert window_from_text(text) is None

    def test_an_impossible_or_reversed_range_gives_no_answer(self):
        assert window_from_text(RANGE.replace("10/10/2026", "31/02/2026")) is None
        assert window_from_text(RANGE.replace("10/01/2027", "01/01/2026")) is None

    def test_no_range_and_no_pdf_give_no_answer_and_do_not_raise(self):
        assert window_from_text("Autorización de Operación RPA") is None
        assert window_from_pdf(io.BytesIO(b"esto no es un PDF")) is None


@pytest.mark.django_db
class TestApprovalCrossesTheWindow:
    def test_a_permit_without_dates_takes_them_from_the_pdf(self):
        permit = _permit(RANGE)

        _approve(permit)

        permit.refresh_from_db()
        assert permit.status == FlightPermission.STATUS_APPROVED
        assert permit.valid_from == date(2026, 10, 10)
        assert permit.valid_until == date(2027, 1, 10)

    def test_matching_dates_approve(self):
        permit = _permit(
            RANGE, valid_from=date(2026, 10, 10), valid_until=date(2027, 1, 10)
        )

        _approve(permit)

        permit.refresh_from_db()
        assert permit.status == FlightPermission.STATUS_APPROVED

    def test_different_dates_block_the_approval_and_say_both(self):
        permit = _permit(
            RANGE, valid_from=date(2026, 10, 11), valid_until=date(2027, 1, 10)
        )

        response = _approve(permit)

        permit.refresh_from_db()
        assert permit.status == FlightPermission.STATUS_REQUESTED
        assert permit.valid_from == date(2026, 10, 11)  # no se pisa
        body = response.content.decode()
        assert "10/10/2026" in body and "11/10/2026" in body

    def test_an_unreadable_pdf_keeps_the_old_gate(self):
        permit = _permit()  # el archivo no es un PDF

        _approve(permit)

        permit.refresh_from_db()
        assert permit.status == FlightPermission.STATUS_REQUESTED
        assert permit.valid_from is None


@pytest.mark.django_db
class TestTheEditScreenSaysWhatFailed:
    def test_a_failed_save_shows_a_summary_at_the_top(self):
        permit = _permit(RANGE)
        permit.status = FlightPermission.STATUS_APPROVED
        permit.save()
        client = login_as("view_flightpermission", "change_flightpermission")

        response = client.post(
            reverse("permission-update", args=[permit.pk]),
            {
                "cost_center": str(permit.cost_center_id),
                "purpose": "photogrammetry",
                "location": "Calama",
                "area_type": "unpopulated",
                "permission_number": "7218",
            },
        )

        assert response.status_code == 200
        body = response.content.decode()
        assert 'id="form-error-summary"' in body
        assert body.index('id="form-error-summary"') < body.index("<fieldset")
