from datetime import date

import pytest
from django.contrib.auth.models import User
from django.db.models import ProtectedError
from django.test import Client
from django.urls import reverse

from apps.core.models import AuditEvent
from apps.registry.models import Aircraft, CostCenter
from .models import MaintenanceHistory, MaintenanceRecord


@pytest.mark.django_db
def test_completing_maintenance_without_required_fields_shows_the_form_again():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="in_progress",
    )
    User.objects.create_superuser("mechanic", "mechanic@test.com", "password")
    client = Client()
    assert client.login(username="mechanic", password="password")

    response = client.post(reverse("maintenance-complete", args=[record.pk]), {})

    assert response.status_code == 200
    assert "completion_form" in response.context
    assert response.context["completion_form"].errors
    record.refresh_from_db()
    assert record.status == "in_progress"


@pytest.mark.django_db
def test_completing_maintenance_with_required_fields_records_history():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="in_progress",
    )
    User.objects.create_superuser("mechanic", "mechanic@test.com", "password")
    client = Client()
    assert client.login(username="mechanic", password="password")

    response = client.post(
        reverse("maintenance-complete", args=[record.pk]),
        {
            "completed_date": "2026-07-24",
            "performed_by": "Contract workshop",
            "notes": "Replaced worn part.",
        },
    )

    assert response.status_code == 302
    record.refresh_from_db()
    assert record.status == "completed"
    assert record.performed_by == "Contract workshop"
    history = MaintenanceHistory.objects.get(record=record)
    assert history.previous_status == "in_progress"
    assert history.new_status == "completed"
    assert history.changed_by == "mechanic"


@pytest.mark.django_db
def test_completing_maintenance_resolves_its_open_alert():
    # LV-26: the "aircraft in maintenance" alert clears when the work is done.
    from django.contrib.contenttypes.models import ContentType

    from apps.compliance.models import Alert, AlertRule

    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="RPA",
        model="M300",
        manufacturer="DJI",
        cost_center=cost_center,
    )
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="check",
        scheduled_date=date(2026, 7, 20),
        status="in_progress",
    )
    rule = AlertRule.objects.create(
        name="Open maintenance",
        entity_type="maintenance.maintenancerecord",
        field_to_watch="status",
    )
    alert = Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(MaintenanceRecord),
        object_id=record.pk,
        message="M300 in maintenance",
    )

    User.objects.create_superuser("mech", "m@t.com", "pw")
    client = Client()
    assert client.login(username="mech", password="pw")
    client.post(
        reverse("maintenance-complete", args=[record.pk]),
        {"completed_date": "2026-07-24", "performed_by": "Shop", "notes": ""},
    )

    alert.refresh_from_db()
    assert alert.is_resolved


@pytest.mark.django_db
def test_aircraft_detail_offers_send_to_maintenance(admin_client):
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-BBB",
        type="RPA",
        model="M300",
        manufacturer="DJI",
        cost_center=cost_center,
    )
    content = admin_client.get(
        reverse("aircraft-detail", args=[aircraft.pk])
    ).content.decode()
    assert reverse("maintenance-create") in content
    assert f"aircraft={aircraft.pk}" in content


@pytest.mark.django_db
def test_record_detail_shows_completion_form_only_while_in_progress():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="in_progress",
    )
    User.objects.create_superuser("mechanic", "mechanic@test.com", "password")
    client = Client()
    assert client.login(username="mechanic", password="password")

    response = client.get(reverse("maintenance-detail", args=[record.pk]))

    assert response.status_code == 200
    assert b'name="performed_by"' in response.content
    assert b'name="completed_date"' in response.content


@pytest.mark.django_db
def test_record_detail_back_link_does_not_rely_on_browser_history():
    """R2.5: same fix as the flight permission detail page -- the status
    actions next to this link redirect back to this same URL, which pushes a
    fresh history entry each time and breaks data-history-back's
    window.history.back()."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="in_progress",
    )
    client = _mechanic_client()

    content = client.get(
        reverse("maintenance-detail", args=[record.pk])
    ).content.decode()

    assert "data-history-back" not in content
    assert reverse("maintenance-list") in content


@pytest.mark.django_db
def test_status_transition_is_audited_with_from_and_to_status():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="pending",
    )
    User.objects.create_superuser("mechanic", "mechanic@test.com", "password")
    client = Client()
    assert client.login(username="mechanic", password="password")

    response = client.post(reverse("maintenance-start", args=[record.pk]))

    assert response.status_code == 302
    event = AuditEvent.objects.latest("created_at")
    assert event.action == "status_changed"
    assert event.model_label == "maintenance.MaintenanceRecord"
    assert event.object_id == str(record.pk)
    assert event.metadata["from_status"] == "pending"
    assert event.metadata["to_status"] == "in_progress"


@pytest.mark.django_db
def test_rejected_status_transition_is_audited_as_rejected():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    # Already in_progress: a start (pending -> in_progress) is not a valid move.
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="in_progress",
    )
    User.objects.create_superuser("mechanic", "mechanic@test.com", "password")
    client = Client()
    assert client.login(username="mechanic", password="password")

    response = client.post(reverse("maintenance-start", args=[record.pk]))

    assert response.status_code == 302
    record.refresh_from_db()
    assert record.status == "in_progress"
    event = AuditEvent.objects.latest("created_at")
    assert event.action == "status_transition_rejected"
    assert event.model_label == "maintenance.MaintenanceRecord"
    assert event.object_id == str(record.pk)


@pytest.mark.django_db
def test_maintenance_record_with_history_cannot_be_hard_deleted():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="in_progress",
    )
    MaintenanceHistory.objects.create(
        record=record,
        previous_status="pending",
        new_status="in_progress",
        changed_by="mechanic",
    )

    with pytest.raises(ProtectedError):
        record.delete()


# ── FASE 4: cover the list view, the create form and the edge branches ────────
def _mechanic_client():
    User.objects.create_superuser("mechanic", "mechanic@test.com", "password")
    client = Client()
    assert client.login(username="mechanic", password="password")
    return client


def _aircraft():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    return Aircraft.objects.create(
        registration="CC-AAA",
        type="RPA",
        model="M300",
        manufacturer="DJI",
        cost_center=cost_center,
    )


@pytest.mark.django_db
def test_maintenance_list_renders_and_filters_by_status_and_type():
    aircraft = _aircraft()
    scheduled = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="pending",
    )
    tbd = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="to_be_defined",
        description="battery check, date TBD",
        status="in_progress",
    )
    client = _mechanic_client()

    full = client.get(reverse("maintenance-list"))
    assert full.status_code == 200
    ids = {r.pk for r in full.context["objects"]}
    assert {scheduled.pk, tbd.pk} <= ids
    # The filter dropdowns are populated from the choices.
    assert full.context["status_choices"] == MaintenanceRecord.STATUSES
    assert full.context["type_choices"] == MaintenanceRecord.TYPES

    by_status = client.get(reverse("maintenance-list"), {"status": "in_progress"})
    assert [r.pk for r in by_status.context["objects"]] == [tbd.pk]
    assert by_status.context["current_status"] == "in_progress"

    by_type = client.get(
        reverse("maintenance-list"), {"maintenance_type": "to_be_defined"}
    )
    assert [r.pk for r in by_type.context["objects"]] == [tbd.pk]
    assert by_type.context["current_type"] == "to_be_defined"


@pytest.mark.django_db
def test_maintenance_list_shows_export_link_and_export_returns_csv():
    """T5.7 (U6): the backend already supported ?export=csv (MList mixes in
    CsvExportMixin), but this template rebuilds `content` from scratch and
    never rendered the link -- unlike every other generic-list page."""
    aircraft = _aircraft()
    MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="pending",
    )
    client = _mechanic_client()

    page = client.get(reverse("maintenance-list"))
    assert "export=csv" in page.content.decode()

    export = client.get(reverse("maintenance-list"), {"export": "csv"})
    assert export.status_code == 200
    assert export["Content-Type"].startswith("text/csv")
    body = b"".join(export.streaming_content).decode()
    assert "100h inspection" in body


@pytest.mark.django_db
def test_maintenance_create_form_renders_and_creates_a_record():
    aircraft = _aircraft()
    client = _mechanic_client()

    form_page = client.get(reverse("maintenance-create"))
    assert form_page.status_code == 200
    assert b'name="maintenance_type"' in form_page.content

    response = client.post(
        reverse("maintenance-create"),
        {
            "aircraft": aircraft.pk,
            "maintenance_type": "to_be_defined",
            "description": "Needs inspection, date to be defined",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("maintenance-list")
    record = MaintenanceRecord.objects.get(aircraft=aircraft)
    assert record.maintenance_type == "to_be_defined"
    assert record.scheduled_date is None  # optional (LV-8b)


@pytest.mark.django_db
def test_completing_an_already_completed_record_does_not_change_it():
    aircraft = _aircraft()
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description="100h inspection",
        scheduled_date=date(2026, 7, 20),
        status="completed",
    )
    client = _mechanic_client()

    # complete is only valid from in_progress; from completed it is rejected
    # (the early-return branch that defers to StatusTransitionView).
    response = client.post(
        reverse("maintenance-complete", args=[record.pk]),
        {"completed_date": "2026-07-25", "performed_by": "Someone"},
    )

    assert response.status_code == 302
    record.refresh_from_db()
    assert record.status == "completed"
    event = AuditEvent.objects.latest("created_at")
    assert event.action == "status_transition_rejected"


@pytest.mark.django_db
def test_completed_record_is_not_incomplete_even_without_a_schedule():
    """models.is_incomplete: a completed record is never 'incomplete', even if
    it is a to_be_defined type with no scheduled date."""
    aircraft = _aircraft()
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="to_be_defined",
        description="done",
        status="completed",
    )
    assert record.is_incomplete is False
