"""LV-79: the document form proposes the dates the linked record already holds.

Uploading the DGAC authorization for a permit meant retyping the validity dates
the permit was created with -- the same information looked up twice.
"""

from datetime import date

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from apps.operations.models import FlightPermission
from apps.registry.models import (
    Aircraft,
    CostCenter,
    Operator,
    Qualification,
    QualificationType,
)


def _client(*codenames):
    user = User.objects.create_user("uploader", password="pw")
    user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username="uploader", password="pw")
    return client


def _permit():
    return FlightPermission.objects.create(
        cost_center=CostCenter.objects.create(code="CC1", name="Uno"),
        purpose="photogrammetry",
        valid_from=date(2026, 8, 1),
        valid_until=date(2026, 8, 31),
        location="Faena Norte",
        area_type="unpopulated",
    )


def _initial_for(client, record):
    content_type = ContentType.objects.get_for_model(type(record))
    response = client.get(
        reverse("document-create"),
        {"entity_type": content_type.pk, "object_id": str(record.pk)},
    )
    assert response.status_code == 200
    return response.context["form"].initial


class TestTheFlightPermitCase:
    @pytest.mark.django_db
    def test_the_permits_validity_window_is_proposed(self, db):
        """The reported case: the permit already carries these dates."""
        permit = _permit()
        client = _client("add_document", "view_document")

        initial = _initial_for(client, permit)

        assert initial["issue_date"] == date(2026, 8, 1)
        assert initial["expiry_date"] == date(2026, 8, 31)

    @pytest.mark.django_db
    def test_the_rendered_form_carries_the_dates(self, db):
        permit = _permit()
        client = _client("add_document", "view_document")
        content_type = ContentType.objects.get_for_model(FlightPermission)

        content = client.get(
            reverse("document-create"),
            {"entity_type": content_type.pk, "object_id": str(permit.pk)},
        ).content.decode()

        assert 'value="2026-08-01"' in content
        assert 'value="2026-08-31"' in content

    @pytest.mark.django_db
    def test_it_says_where_the_dates_came_from(self, db):
        """A pre-filled field with no explanation reads as a value someone else
        entered, and nobody dares correct it."""
        permit = _permit()
        client = _client("add_document", "view_document")
        content_type = ContentType.objects.get_for_model(FlightPermission)

        content = client.get(
            reverse("document-create"),
            {"entity_type": content_type.pk, "object_id": str(permit.pk)},
        ).content.decode()

        assert "Tomada del registro enlazado" in content

    @pytest.mark.django_db
    def test_an_explicit_url_date_still_wins(self, db):
        """An explicit request beats a derived suggestion."""
        permit = _permit()
        client = _client("add_document", "view_document")
        content_type = ContentType.objects.get_for_model(FlightPermission)

        response = client.get(
            reverse("document-create"),
            {
                "entity_type": content_type.pk,
                "object_id": str(permit.pk),
                "issue_date": "2026-07-15",
            },
        )

        assert response.context["form"].initial["issue_date"] == "2026-07-15"

    @pytest.mark.django_db
    def test_nothing_is_forced_the_user_can_override(self, db):
        """The suggestion is editable: the DGAC can issue a resolution on a
        date of its own."""
        permit = _permit()
        client = _client("add_document", "view_document")
        content_type = ContentType.objects.get_for_model(FlightPermission)
        doc_type = _doc_type()

        client.post(
            reverse("document-create"),
            {
                "doc_type": doc_type.pk,
                "entity_type": content_type.pk,
                "object_id": str(permit.pk),
                "issue_date": "2026-07-20",
                "expiry_date": "2026-09-30",
                "file": _pdf(),
            },
        )

        from apps.compliance.models import Document

        document = Document.objects.get()
        assert document.issue_date == date(2026, 7, 20)
        assert document.expiry_date == date(2026, 9, 30)


class TestWhereTheMappingIsAmbiguous:
    @pytest.mark.django_db
    def test_a_qualification_maps_one_to_one(self, db):
        operator = Operator.objects.create(employee_id="P1", full_name="Pilot One")
        qualification = Qualification.objects.create(
            operator=operator,
            qualification_type=QualificationType.objects.create(
                code="dgac", name="Credencial"
            ),
            issue_date=date(2026, 1, 15),
            expiry_date=date(2028, 1, 15),
        )
        client = _client("add_document", "view_document")

        initial = _initial_for(client, qualification)

        assert initial["issue_date"] == date(2026, 1, 15)
        assert initial["expiry_date"] == date(2028, 1, 15)

    @pytest.mark.django_db
    def test_an_aircraft_proposes_nothing(self, db):
        """An aircraft carries several dates (insurance, airworthiness) and
        which one applies depends on the document type. Guessing wrong there is
        worse than not guessing."""
        aircraft = Aircraft.objects.create(
            registration="CC-A1",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            insurance_expiry=date(2026, 12, 31),
        )
        client = _client("add_document", "view_document")

        initial = _initial_for(client, aircraft)

        assert "issue_date" not in initial
        assert "expiry_date" not in initial

    @pytest.mark.django_db
    def test_an_archived_record_proposes_nothing(self, db):
        permit = _permit()
        permit.is_active = False
        permit.save(update_fields=["is_active"])
        client = _client("add_document", "view_document")

        initial = _initial_for(client, permit)

        assert "issue_date" not in initial

    @pytest.mark.django_db
    def test_no_linked_record_proposes_nothing(self, db):
        """Reaching the form from the menu, with nothing selected yet."""
        client = _client("add_document", "view_document")

        response = client.get(reverse("document-create"))

        assert "issue_date" not in response.context["form"].initial


def _doc_type():
    from apps.compliance.models import DocumentType

    return DocumentType.objects.create(name="Autorización DGAC", code="AUT")


def _pdf():
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        "auth.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
    )


@pytest.fixture(autouse=True)
def _isolated_storage(settings, tmp_path):
    settings.DOCUMENTS_ANTIVIRUS_COMMAND = ""
    settings.DOCUMENTS_DIR = str(tmp_path)
