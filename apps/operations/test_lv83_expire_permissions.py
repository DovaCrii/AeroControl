"""LV-83: a permit closes on its own when its authorization window runs out.

The decision this encodes (user, 2026-08-13): **expired is not completed**.
Completed means the work was flown *and* the signed DGAC authorization is on
file -- R2.4 refuses that transition without it -- so a job that auto-completed
permits would walk through that guard. Expired only means the window closed, and
a permit can expire having flown nothing, which is exactly what
`on_time_execution` counts.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.compliance.kpis import on_time_execution
from apps.operations.models import FlightPermission, PermissionHistory
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()


def _permit(**kwargs):
    cost_center = kwargs.pop("cost_center", None) or CostCenter.objects.create(
        code=f"CC{FlightPermission.objects.count()}"
    )
    return FlightPermission.objects.create(
        cost_center=cost_center,
        purpose="photogrammetry",
        valid_from=kwargs.pop("valid_from", TODAY - timedelta(days=30)),
        valid_until=kwargs.pop("valid_until", TODAY - timedelta(days=1)),
        location="Site",
        **kwargs,
    )


@pytest.mark.django_db
class TestWhatItCloses:
    @pytest.mark.parametrize("status", ["requested", "approved"])
    def test_an_open_permit_past_its_window_is_expired(self, status):
        permit = _permit(status=status)

        call_command("expire_permissions")

        permit.refresh_from_db()
        assert permit.status == FlightPermission.STATUS_EXPIRED

    def test_a_permit_still_inside_its_window_is_untouched(self):
        permit = _permit(valid_until=TODAY, status="approved")

        call_command("expire_permissions")

        permit.refresh_from_db()
        assert permit.status == "approved"

    def test_valid_until_is_inclusive(self):
        """The permit is good *through* its last day, so "today" is not over."""
        permit = _permit(valid_until=TODAY, status="requested")

        call_command("expire_permissions")

        permit.refresh_from_db()
        assert permit.status == "requested"

    @pytest.mark.parametrize("status", ["completed", "denied"])
    def test_already_closed_permits_are_left_alone(self, status):
        """Re-closing a completed permit would erase that it was flown; a denied
        one never became an authorization to begin with."""
        permit = _permit(status=status)

        call_command("expire_permissions")

        permit.refresh_from_db()
        assert permit.status == status

    def test_an_archived_permit_is_not_touched(self):
        permit = _permit(status="approved", is_active=False)

        call_command("expire_permissions")

        permit.refresh_from_db()
        assert permit.status == "approved"

    def test_running_twice_does_not_write_a_second_history_row(self):
        permit = _permit(status="approved")

        call_command("expire_permissions")
        call_command("expire_permissions")

        assert PermissionHistory.objects.filter(permission=permit).count() == 1


@pytest.mark.django_db
class TestTheTrace:
    def test_the_closure_is_recorded_with_the_job_as_the_actor(self):
        """Not the generic "system" fallback: an auditor should see *what*
        closed the permit, not merely that no human did."""
        permit = _permit(status="approved")

        call_command("expire_permissions")

        entry = PermissionHistory.objects.get(permission=permit)
        assert entry.previous_status == "approved"
        assert entry.new_status == FlightPermission.STATUS_EXPIRED
        assert entry.changed_by == "expire_permissions"

    def test_the_stepper_shows_how_far_it_got(self):
        """An expired permit that had been approved must not read "Solicitado ✕
        Caducado" -- that hides that the DGAC had authorized it, which is the
        fact an auditor is looking for."""
        permit = _permit(status="approved")
        call_command("expire_permissions")
        permit.refresh_from_db()

        steps = permit.status_steps()

        assert [(step["code"], step["state"]) for step in steps] == [
            ("requested", "done"),
            ("approved", "done"),
            ("expired", "blocked"),
        ]

    def test_a_permit_that_expired_without_being_approved_stops_earlier(self):
        permit = _permit(status="requested")
        call_command("expire_permissions")
        permit.refresh_from_db()

        assert [(step["code"], step["state"]) for step in permit.status_steps()] == [
            ("requested", "done"),
            ("expired", "blocked"),
        ]

    def test_denied_still_renders_as_before(self):
        """The second terminal state must not change how the first one reads."""
        permit = _permit(status="denied")

        assert [step["state"] for step in permit.status_steps()] == ["done", "blocked"]


@pytest.mark.django_db
class TestDryRun:
    def test_it_reports_without_writing(self):
        permit = _permit(status="approved")

        call_command("expire_permissions", "--dry-run")

        permit.refresh_from_db()
        assert permit.status == "approved"
        assert not PermissionHistory.objects.exists()


@pytest.mark.django_db
class TestTheKpiSurvivesIt:
    def test_an_expired_permit_with_no_flights_still_counts_as_a_failure(self):
        """The regression this guards against: `on_time_execution` used to
        filter on approved/completed, so once the job moved a lapsed permit to
        `expired` the KPI would quietly stop counting its own failures and drift
        towards a meaningless 100%."""
        _permit(status="approved", valid_until=TODAY - timedelta(days=2))

        call_command("expire_permissions")

        result = on_time_execution(TODAY - timedelta(days=30), TODAY)
        assert result["total"] == 1
        assert result["on_time"] == 0
        assert result["pct"] == 0.0

    def test_a_flown_permit_still_counts_as_on_time(self):
        from apps.operations.models import FlightRecord

        permit = _permit(status="approved", valid_until=TODAY - timedelta(days=2))
        aircraft = Aircraft.objects.create(
            registration="CC-KPI", type="RPA", model="M3", manufacturer="DJI"
        )
        operator = Operator.objects.create(employee_id="E-KPI", full_name="Pilot")
        FlightRecord.objects.create(
            permission=permit,
            aircraft=aircraft,
            pilot=operator,
            actual_date=TODAY - timedelta(days=5),
            departure_time="09:00",
            arrival_time="10:30",
        )

        call_command("expire_permissions")

        result = on_time_execution(TODAY - timedelta(days=30), TODAY)
        assert result["total"] == 1
        assert result["on_time"] == 1
