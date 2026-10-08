"""LV-294: las fechas de un documento de permiso salen del propio permiso.

Pedido del usuario (2026-10-08, con la autorización de la DGAC abierta al lado): el
rango de fechas autorizado ya está en el permiso, y teclearlo otra vez sólo permite
equivocarse. Si se dejan en blanco se toman de la vigencia del permiso; una fecha
escrita a mano se respeta.
"""

from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.compliance.forms import DocumentForm
from apps.compliance.models import DocumentType
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter

PDF = b"%PDF-1.4\n%test\n"


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


@pytest.fixture
def permit(centre):
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        permission_number="7218",
        location="Sector 3",
        area_type="unpopulated",
        valid_from=date(2026, 10, 10),
        valid_until=date(2027, 1, 10),
    )


@pytest.fixture
def authorization(db):
    return DocumentType.objects.create(
        code="auth-test", name="Autorización", requires_expiry=True
    )


def _form(entity, record, doc_type, **dates):
    content_type = ContentType.objects.get_for_model(entity)
    data = {
        "entity_type": str(content_type.pk),
        "object_id": str(record.pk),
        "doc_type": str(doc_type.pk),
        **dates,
    }
    files = {"file": SimpleUploadedFile("a.pdf", PDF, content_type="application/pdf")}
    return DocumentForm(data=data, files=files)


@pytest.mark.django_db
class TestDatesFromThePermit:
    def test_blank_dates_are_taken_from_the_permit(self, permit, authorization):
        form = _form(FlightPermission, permit, authorization)

        assert form.is_valid(), form.errors
        assert form.cleaned_data["issue_date"] == date(2026, 10, 10)
        assert form.cleaned_data["expiry_date"] == date(2027, 1, 10)

    def test_a_date_typed_by_hand_is_respected(self, permit, authorization):
        form = _form(
            FlightPermission,
            permit,
            authorization,
            issue_date="2026-10-12",
            expiry_date="2027-01-05",
        )

        assert form.is_valid(), form.errors
        assert form.cleaned_data["issue_date"] == date(2026, 10, 12)
        assert form.cleaned_data["expiry_date"] == date(2027, 1, 5)

    def test_only_the_blank_one_is_filled(self, permit, authorization):
        form = _form(FlightPermission, permit, authorization, issue_date="2026-10-12")

        assert form.is_valid(), form.errors
        assert form.cleaned_data["issue_date"] == date(2026, 10, 12)
        assert form.cleaned_data["expiry_date"] == date(2027, 1, 10)

    def test_the_generated_title_uses_the_permit_date(self, permit, authorization):
        form = _form(FlightPermission, permit, authorization)

        assert form.is_valid(), form.errors
        assert "2026-10-10" in form.cleaned_data["title"]

    def test_another_entity_still_needs_its_issue_date(self, centre, authorization):
        aircraft = Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=centre,
        )

        form = _form(Aircraft, aircraft, authorization, expiry_date="2027-01-01")

        assert not form.is_valid()
        assert "issue_date" in form.errors
