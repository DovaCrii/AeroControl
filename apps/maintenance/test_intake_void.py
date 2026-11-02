"""LV-388: «Anular ingreso» archiva el ingreso y su mantención; no borra nada.

Datos ficticios solamente; el almacenamiento apunta a un `tmp_path`.
"""

import pytest
from django.urls import reverse

from apps.compliance.models import Document
from apps.core.models import AuditEvent, OperationalTenant
from apps.core.testing import login_as
from apps.maintenance.models import MaintenanceRecord, WorkshopIntake
from apps.maintenance.test_intake_views import (
    aircraft,
    operator_client,
    reception_pdf,
    register,
)

pytestmark = pytest.mark.django_db

VOID = "maintenance-void-intake"


@pytest.fixture(autouse=True)
def documents_root(settings, tmp_path):
    settings.DOCUMENTS_ROOT = tmp_path
    return tmp_path


def _registered(plane=None, client=None):
    plane = plane or aircraft()
    register(client or operator_client(), reception_pdf(), plane)
    return plane, MaintenanceRecord.objects.get(aircraft=plane)


def _manager(*extra, **kwargs):
    return login_as(
        "change_maintenancerecord", "view_maintenancerecord", *extra, **kwargs
    )


def _post(client, record):
    return client.post(reverse(VOID, args=[record.pk]))


def _detail(client, record):
    return client.get(reverse("maintenance-detail", args=[record.pk]))


class TestVoid:
    def test_it_needs_change_maintenancerecord(self):
        _plane, record = _registered()
        client = login_as("view_maintenancerecord")
        assert _post(client, record).status_code == 403
        record.refresh_from_db()
        assert record.is_active

    def test_get_is_not_allowed(self):
        _plane, record = _registered()
        assert _manager().get(reverse(VOID, args=[record.pk])).status_code == 405

    def test_it_archives_the_intake_and_the_record_and_deletes_nothing(self):
        _plane, record = _registered()
        document = Document.objects.get()

        response = _post(_manager(), record)

        assert response.status_code == 302
        assert response.url == reverse("maintenance-list")
        record.refresh_from_db()
        intake = WorkshopIntake.objects.get(record=record)
        assert not record.is_active and not intake.is_active
        assert MaintenanceRecord.objects.count() == 1
        assert WorkshopIntake.objects.count() == 1
        # El documento sigue ahí, activo y en la aeronave.
        document.refresh_from_db()
        assert document.is_active
        assert intake.source_document_id == document.pk

    def test_it_is_audited(self):
        _plane, record = _registered()
        _post(_manager(), record)
        assert AuditEvent.objects.filter(action="workshop_intake_voided").count() == 1

    def test_it_leaves_the_list_and_the_fiche(self):
        _plane, record = _registered()
        client = _manager()
        _post(client, record)
        assert _detail(client, record).status_code == 404
        listing = client.get(reverse("maintenance-list"))
        assert record.pk not in [o.pk for o in listing.context["objects"]]

    def test_a_second_void_does_nothing(self):
        _plane, record = _registered()
        client = _manager()
        _post(client, record)
        assert _post(client, record).status_code == 404

    def test_another_tenant_cannot_void_it(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        _plane, record = _registered(
            aircraft(tenant=b),
            login_as("add_maintenancerecord", "add_document", member_of=b),
        )
        assert _post(_manager(member_of=a), record).status_code == 404
        record.refresh_from_db()
        assert record.is_active


class TestAircraftState:
    def test_the_aircraft_that_this_intake_took_away_is_restored(self):
        plane, record = _registered()
        plane.refresh_from_db()
        assert (plane.status, plane.current_location) == ("maintenance", "maintenance")

        _post(_manager(), record)

        plane.refresh_from_db()
        assert (plane.status, plane.current_location) == ("active", "headquarters")

    def test_it_is_not_touched_when_another_open_record_keeps_it_at_the_workshop(self):
        plane, record = _registered()
        other = MaintenanceRecord.objects.create(
            aircraft=plane, maintenance_type="unscheduled", description="otra"
        )
        other.status = "sent"
        other.save()

        response = _post(_manager(), record)

        plane.refresh_from_db()
        assert (plane.status, plane.current_location) == ("maintenance", "maintenance")
        msgs = [str(m) for m in response.wsgi_request._messages]
        assert any("not changed" in m or "no se cambi" in m for m in msgs)

    def test_it_is_not_touched_when_somebody_already_changed_it(self):
        plane, record = _registered()
        plane.status = "damaged"
        plane.save(update_fields=["status", "updated_at"])

        _post(_manager(), record)

        plane.refresh_from_db()
        assert plane.status == "damaged"

    def test_a_record_that_never_left_does_not_move_the_aircraft(self):
        plane = aircraft()
        record = MaintenanceRecord.objects.create(
            aircraft=plane, maintenance_type="unscheduled", description="x"
        )
        WorkshopIntake.objects.create(
            record=record, workshop_name="Geocom", workshop_order="TEST-7"
        )
        before = (plane.status, plane.current_location)

        _post(_manager(), record)

        plane.refresh_from_db()
        assert (plane.status, plane.current_location) == before
        record.refresh_from_db()
        assert not record.is_active


class TestButton:
    def test_it_shows_for_an_active_intake_with_the_permission(self):
        _plane, record = _registered()
        html = _detail(_manager(), record).content.decode()
        assert f'action="{reverse(VOID, args=[record.pk])}"' in html

    def test_it_is_absent_without_the_permission(self):
        _plane, record = _registered()
        html = _detail(login_as("view_maintenancerecord"), record).content.decode()
        assert reverse(VOID, args=[record.pk]) not in html

    def test_it_is_absent_when_the_record_has_no_intake(self):
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft(), maintenance_type="unscheduled", description="x"
        )
        html = _detail(_manager(), record).content.decode()
        assert reverse(VOID, args=[record.pk]) not in html

    def test_it_is_absent_when_the_intake_is_already_void(self):
        _plane, record = _registered()
        WorkshopIntake.objects.filter(record=record).update(is_active=False)
        html = _detail(_manager(), record).content.decode()
        assert reverse(VOID, args=[record.pk]) not in html
