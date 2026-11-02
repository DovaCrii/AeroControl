"""LV-389: «Anular» desde la lista, para un ingreso activo o una pendiente virgen.

Datos ficticios solamente; el almacenamiento apunta a un `tmp_path`.
"""

import pytest
from django.urls import reverse

from apps.compliance.models import Alert, Document
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

VOID = "maintenance-void"


@pytest.fixture(autouse=True)
def documents_root(settings, tmp_path):
    settings.DOCUMENTS_ROOT = tmp_path
    return tmp_path


def _manager(*extra, **kwargs):
    return login_as(
        "change_maintenancerecord", "view_maintenancerecord", *extra, **kwargs
    )


def _pending(plane=None):
    return MaintenanceRecord.objects.create(
        aircraft=plane or aircraft(), maintenance_type="unscheduled", description="x"
    )


def _in_state(status):
    record = _pending()
    record.status = status
    record.save()
    return record


def _post(client, record):
    return client.post(reverse(VOID, args=[record.pk]))


def _list_html(client):
    return client.get(reverse("maintenance-list")).content.decode()


def _row_form(html, record):
    return f'action="{reverse(VOID, args=[record.pk])}"' in html


class TestVoidPending:
    def test_a_never_started_pending_record_is_archived_and_nothing_deleted(self):
        plane = aircraft()
        record = _pending(plane)
        before = (plane.status, plane.current_location)

        response = _post(_manager(), record)

        assert response.status_code == 302
        assert response.url == reverse("maintenance-list")
        record.refresh_from_db()
        assert not record.is_active
        assert MaintenanceRecord.objects.count() == 1
        plane.refresh_from_db()
        assert (plane.status, plane.current_location) == before
        event = AuditEvent.objects.get(action="maintenance_voided")
        assert set(event.metadata) <= {"query_keys"}

    def test_open_alerts_are_resolved(self):
        from django.contrib.contenttypes.models import ContentType

        from apps.compliance.models import AlertRule

        record = _pending()
        rule = AlertRule.objects.create(
            name="Test rule",
            entity_type="maintenancerecord",
            field_to_watch="scheduled_date",
            days_before_expiry=30,
        )
        alert = Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(MaintenanceRecord),
            object_id=record.pk,
            message="Due soon",
        )
        _post(_manager(), record)
        alert.refresh_from_db()
        assert alert.is_resolved

    @pytest.mark.parametrize("status", ["in_progress", "sent", "at_workshop"])
    def test_a_record_in_progress_or_sent_is_not_voided(self, status):
        record = _in_state(status)
        response = _post(_manager(), record)
        assert response.status_code == 302
        assert response.url == reverse("maintenance-detail", args=[record.pk])
        record.refresh_from_db()
        assert record.is_active
        assert not AuditEvent.objects.filter(action="maintenance_voided").exists()

    def test_a_pending_record_with_history_is_not_voided(self):
        record = _in_state("in_progress")
        record.status = "pending"
        record.save()
        assert record.history.exists()
        _post(_manager(), record)
        record.refresh_from_db()
        assert record.is_active

    def test_a_cancelled_workshop_record_is_not_voided(self):
        record = _in_state("cancelled")
        _post(_manager(), record)
        record.refresh_from_db()
        assert record.is_active


class TestVoidIntake:
    def test_an_active_intake_is_voided_with_its_own_audit_action(self):
        plane = aircraft()
        register(operator_client(), reception_pdf(), plane)
        record = MaintenanceRecord.objects.get(aircraft=plane)
        document = Document.objects.get()

        _post(_manager(), record)

        record.refresh_from_db()
        assert not record.is_active
        assert not WorkshopIntake.objects.get(record=record).is_active
        document.refresh_from_db()
        assert document.is_active
        assert AuditEvent.objects.filter(action="workshop_intake_voided").count() == 1
        assert not AuditEvent.objects.filter(action="maintenance_voided").exists()

    def test_the_old_route_still_works(self):
        record = _pending()
        client = _manager()
        response = client.post(reverse("maintenance-void-intake", args=[record.pk]))
        assert response.status_code == 302
        record.refresh_from_db()
        assert not record.is_active


class TestAccess:
    def test_it_needs_change_maintenancerecord(self):
        record = _pending()
        assert _post(login_as("view_maintenancerecord"), record).status_code == 403
        record.refresh_from_db()
        assert record.is_active

    def test_get_is_not_allowed(self):
        record = _pending()
        assert _manager().get(reverse(VOID, args=[record.pk])).status_code == 405

    def test_another_tenant_cannot_void_it(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        record = _pending(aircraft(tenant=b))
        assert _post(_manager(member_of=a), record).status_code == 404
        record.refresh_from_db()
        assert record.is_active


class TestButtons:
    def test_list_shows_it_for_a_voidable_record_only(self):
        pending = _pending()
        busy = MaintenanceRecord.objects.create(
            aircraft=aircraft("TST-2", "SER-2"),
            maintenance_type="unscheduled",
            description="y",
        )
        busy.status = "in_progress"
        busy.save()
        html = _list_html(_manager())
        assert _row_form(html, pending)
        assert not _row_form(html, busy)

    def test_list_shows_it_for_an_active_intake(self):
        plane = aircraft()
        register(operator_client(), reception_pdf(), plane)
        record = MaintenanceRecord.objects.get(aircraft=plane)
        assert _row_form(_list_html(_manager()), record)

    def test_list_hides_it_without_the_permission(self):
        pending = _pending()
        html = _list_html(login_as("view_maintenancerecord"))
        assert not _row_form(html, pending)
        assert "data-void-row" not in html

    def test_fiche_shows_it_for_a_pending_record_with_its_own_confirmation(self):
        record = _pending()
        html = (
            _manager().get(reverse("maintenance-detail", args=[record.pk])).content
        ).decode()
        assert _row_form(html, record)
        assert "never started or sent" in html or "Nunca se inició" in html

    def test_fiche_hides_it_for_a_record_in_progress(self):
        record = _in_state("in_progress")
        html = (
            _manager().get(reverse("maintenance-detail", args=[record.pk])).content
        ).decode()
        assert not _row_form(html, record)
