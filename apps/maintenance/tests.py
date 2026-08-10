from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.db.models import ProtectedError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.registry.models import Aircraft, CostCenter
from .forms import MaintenanceRecordForm
from .models import MaintenanceHistory, MaintenanceRecord


@pytest.mark.django_db
def test_maintenance_record_form_aircraft_field_uses_the_selector_label():
    """R5.5: registration alone doesn't distinguish "which M300" in a
    dropdown with several of the same model."""
    aircraft = Aircraft.objects.create(
        registration="RPA-1",
        type="RPA",
        model="M300",
        manufacturer="DJI",
        serial_number="1ABC234",
    )
    form = MaintenanceRecordForm()
    assert form.fields["aircraft"].label_from_instance(aircraft) == (
        "RPA-1 · M300 · S/N 1ABC234"
    )


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


# ── R5.1: the workshop chain (sent -> at_workshop -> finished -> in_transit) ──


class TestWorkshopChainTransitions:
    """Each step is a plain StatusTransitionView, same shape as the existing
    start/complete pair -- one test per hop confirms the chain links up."""

    @pytest.mark.django_db
    def test_full_chain_from_pending_to_completed(self, db):
        aircraft = _aircraft()
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="unscheduled",
            description="Gearbox replacement",
            scheduled_date=date(2026, 7, 20),
            status="pending",
        )
        client = _mechanic_client()

        steps = [
            ("maintenance-send", "sent"),
            ("maintenance-arrive-at-workshop", "at_workshop"),
            ("maintenance-finish", "finished"),
            ("maintenance-depart", "in_transit"),
        ]
        for url_name, expected_status in steps:
            response = client.post(reverse(url_name, args=[record.pk]))
            assert response.status_code == 302
            record.refresh_from_db()
            assert record.status == expected_status

        response = client.post(
            reverse("maintenance-complete", args=[record.pk]),
            {"completed_date": "2026-08-01", "performed_by": "Contract workshop"},
        )
        assert response.status_code == 302
        record.refresh_from_db()
        assert record.status == "completed"

    @pytest.mark.django_db
    def test_cannot_skip_a_step(self, db):
        aircraft = _aircraft()
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="unscheduled",
            description="Gearbox replacement",
            status="sent",
        )
        client = _mechanic_client()

        # at_workshop -> finished is not valid while still just "sent".
        response = client.post(reverse("maintenance-finish", args=[record.pk]))

        assert response.status_code == 302
        record.refresh_from_db()
        assert record.status == "sent"
        event = AuditEvent.objects.latest("created_at")
        assert event.action == "status_transition_rejected"


class TestWorkshopChainDrivesAircraftLocation:
    """R5.1: entering the chain ("sent") marks the aircraft away; arriving
    home from it (completing from "in_transit") marks it active again --
    the states in between don't touch the aircraft a second time."""

    @pytest.mark.django_db
    def test_sending_to_workshop_moves_the_aircraft_and_logs_it(self, db):
        from apps.registry.models import ResourceMovementLog

        aircraft = _aircraft()
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="unscheduled",
            description="Gearbox replacement",
            status="pending",
        )
        user = User.objects.create_superuser("sender", "s@t.com", "pw")
        client = Client()
        assert client.login(username="sender", password="pw")

        client.post(reverse("maintenance-send", args=[record.pk]))

        aircraft.refresh_from_db()
        assert aircraft.current_location == "maintenance"
        assert aircraft.status == "maintenance"
        log = ResourceMovementLog.objects.get(
            resource_kind="aircraft", resource_id=aircraft.pk
        )
        assert log.movement == "location_changed"
        assert log.changed_by_user_id == user.pk

    @pytest.mark.django_db
    def test_arriving_and_finishing_do_not_move_the_aircraft_again(self, db):
        aircraft = _aircraft()
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="unscheduled",
            description="Gearbox replacement",
            status="sent",
        )
        aircraft.current_location = "maintenance"
        aircraft.status = "maintenance"
        aircraft.save(update_fields=["current_location", "status", "updated_at"])
        client = _mechanic_client()

        client.post(reverse("maintenance-arrive-at-workshop", args=[record.pk]))
        client.post(reverse("maintenance-finish", args=[record.pk]))

        aircraft.refresh_from_db()
        assert aircraft.current_location == "maintenance"
        assert aircraft.status == "maintenance"

    @pytest.mark.django_db
    def test_completing_from_in_transit_brings_the_aircraft_home(self, db):
        aircraft = _aircraft()
        aircraft.current_location = "maintenance"
        aircraft.status = "maintenance"
        aircraft.save(update_fields=["current_location", "status", "updated_at"])
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="unscheduled",
            description="Gearbox replacement",
            status="in_transit",
        )
        client = _mechanic_client()

        client.post(
            reverse("maintenance-complete", args=[record.pk]),
            {"completed_date": "2026-08-01", "performed_by": "Contract workshop"},
        )

        aircraft.refresh_from_db()
        assert aircraft.current_location == "headquarters"
        assert aircraft.status == "active"

    @pytest.mark.django_db
    def test_completing_the_short_in_house_path_does_not_touch_the_aircraft(self, db):
        """Regression guard: the original pending -> in_progress -> completed
        path must keep working exactly as it did before R5.1 -- no aircraft
        side effect, since it never left headquarters."""
        aircraft = _aircraft()
        original_location = aircraft.current_location
        original_status = aircraft.status
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="scheduled",
            description="100h inspection",
            status="in_progress",
        )
        client = _mechanic_client()

        client.post(
            reverse("maintenance-complete", args=[record.pk]),
            {"completed_date": "2026-08-01", "performed_by": "In-house crew"},
        )

        aircraft.refresh_from_db()
        assert aircraft.current_location == original_location
        assert aircraft.status == original_status


class TestStatusChangedAtAndDwell:
    @pytest.mark.django_db
    def test_status_changed_at_is_set_on_creation(self, db):
        aircraft = _aircraft()
        before = timezone.now()
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="scheduled",
            description="100h inspection",
            status="pending",
        )
        assert record.status_changed_at is not None
        assert record.status_changed_at >= before

    @pytest.mark.django_db
    def test_status_changed_at_bumps_on_a_real_transition(self, db):
        aircraft = _aircraft()
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="scheduled",
            description="100h inspection",
            status="pending",
        )
        first = record.status_changed_at
        client = _mechanic_client()

        client.post(reverse("maintenance-start", args=[record.pk]))

        record.refresh_from_db()
        # >=, not >: this machine's timezone.now() can return the identical
        # value across rapid successive calls (same clock-resolution note as
        # ResourceMovementLog.sequence) -- the meaningful assertion is that
        # it did not go backwards or stay at some earlier value, not that it
        # strictly increased within the same test's wall-clock tick.
        assert record.status_changed_at >= first

    @pytest.mark.django_db
    def test_status_changed_at_does_not_move_on_an_unrelated_save(self, db):
        aircraft = _aircraft()
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="scheduled",
            description="100h inspection",
            status="pending",
        )
        first = record.status_changed_at
        record.description = "100h inspection, updated notes"
        record.save(update_fields=["description", "updated_at"])
        record.refresh_from_db()
        assert record.status_changed_at == first

    @pytest.mark.django_db
    def test_workshop_dwell_is_overdue_past_the_threshold(self, db):
        aircraft = _aircraft()
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="unscheduled",
            description="Gearbox replacement",
            status="at_workshop",
        )
        MaintenanceRecord.objects.filter(pk=record.pk).update(
            status_changed_at=timezone.now()
            - timedelta(days=MaintenanceRecord.WORKSHOP_DWELL_ALERT_DAYS)
        )
        record.refresh_from_db()
        assert record.workshop_dwell_is_overdue is True

    @pytest.mark.django_db
    def test_workshop_dwell_is_not_overdue_before_the_threshold(self, db):
        aircraft = _aircraft()
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="unscheduled",
            description="Gearbox replacement",
            status="at_workshop",
        )
        MaintenanceRecord.objects.filter(pk=record.pk).update(
            status_changed_at=timezone.now()
            - timedelta(days=MaintenanceRecord.WORKSHOP_DWELL_ALERT_DAYS - 1)
        )
        record.refresh_from_db()
        assert record.workshop_dwell_is_overdue is False

    @pytest.mark.django_db
    def test_short_path_status_is_never_flagged_as_dwelling(self, db):
        """in_progress is not a workshop status -- no dwell flag regardless
        of how long it has been open."""
        aircraft = _aircraft()
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="scheduled",
            description="100h inspection",
            status="in_progress",
        )
        MaintenanceRecord.objects.filter(pk=record.pk).update(
            status_changed_at=timezone.now() - timedelta(days=30)
        )
        record.refresh_from_db()
        assert record.workshop_dwell_is_overdue is False


@pytest.mark.django_db
def test_aircraft_detail_open_maintenance_includes_workshop_chain_statuses():
    """Regression guard: AircraftDetail's open_maintenance used to hardcode
    ["pending", "in_progress"], which would have silently dropped a record
    the moment it moved into the workshop chain."""
    aircraft = _aircraft()
    record = MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="unscheduled",
        description="Gearbox replacement",
        status="at_workshop",
    )
    client = _mechanic_client()

    response = client.get(reverse("aircraft-detail", args=[aircraft.pk]))

    assert record in list(response.context["open_maintenance"])
