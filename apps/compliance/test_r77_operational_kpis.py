"""R7.7: the two operational KPIs derivable today (ISO 9001 9.1.1).

The clause wants a target, a trend and action when the target is missed. These
cover value and target; the trend for document counters comes from
ComplianceSnapshot, already built.
"""

from datetime import date, time, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse

from apps.compliance.kpis import (
    FLEET_AVAILABILITY_TARGET,
    fleet_availability,
    on_time_execution,
    operational_kpis,
)
from apps.operations.models import FlightPermission, FlightRecord
from apps.registry.models import Aircraft, CostCenter, Operator

START = date(2026, 8, 1)
END = date(2026, 8, 31)


def _aircraft(registration, status="active"):
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3",
        manufacturer="DJI",
        status=status,
    )


def _permit(cost_center, valid_until, status="approved"):
    return FlightPermission.objects.create(
        cost_center=cost_center,
        purpose="photogrammetry",
        valid_from=valid_until - timedelta(days=5),
        valid_until=valid_until,
        location="Faena",
        area_type="unpopulated",
        status=status,
    )


class TestFleetAvailability:
    @pytest.mark.django_db
    def test_counts_only_flyable_aircraft(self, db):
        _aircraft("CC-A1")
        _aircraft("CC-A2")
        _aircraft("CC-A3", status="maintenance")
        _aircraft("CC-A4", status="damaged")

        result = fleet_availability()

        assert result["total"] == 4
        assert result["available"] == 2
        assert result["pct"] == 50.0

    @pytest.mark.django_db
    def test_retired_aircraft_leave_the_denominator(self, db):
        """A decommissioned aircraft is not unavailable -- it left the fleet.
        Counting it would make the number sag permanently for a good
        decision."""
        _aircraft("CC-A1")
        _aircraft("CC-A2", status="retired")

        result = fleet_availability()

        assert result["total"] == 1
        assert result["pct"] == 100.0

    @pytest.mark.django_db
    def test_no_fleet_gives_no_percentage(self, db):
        """None, not 0.0: zero would read as total failure where the honest
        answer is that the question does not apply."""
        assert fleet_availability()["pct"] is None

    @pytest.mark.django_db
    def test_carries_the_agreed_target(self, db):
        _aircraft("CC-A1")

        assert fleet_availability()["target"] == FLEET_AVAILABILITY_TARGET


class TestOnTimeExecution:
    @pytest.fixture
    def cost_center(self, db):
        return CostCenter.objects.create(code="CC1", name="Uno")

    @pytest.mark.django_db
    def test_a_permit_flown_within_its_window_counts_as_on_time(self, cost_center):
        permit = _permit(cost_center, date(2026, 8, 10))
        pilot = Operator.objects.create(employee_id="P1", full_name="Pilot One")
        aircraft = _aircraft("CC-A1")
        permit.operators.add(pilot)
        permit.aircraft_fleet.add(aircraft)
        FlightRecord.objects.create(
            permission=permit,
            actual_date=date(2026, 8, 8),
            departure_time=time(9, 0),
            arrival_time=time(10, 0),
            pilot=pilot,
            aircraft=aircraft,
        )

        result = on_time_execution(START, END)

        assert result["total"] == 1
        assert result["on_time"] == 1
        assert result["pct"] == 100.0

    @pytest.mark.django_db
    def test_a_permit_that_expired_unflown_is_the_failure_measured(self, cost_center):
        _permit(cost_center, date(2026, 8, 10))

        result = on_time_execution(START, END)

        assert result["total"] == 1
        assert result["on_time"] == 0
        assert result["pct"] == 0.0

    @pytest.mark.django_db
    def test_a_permit_still_open_is_not_counted(self, cost_center):
        """It has not failed anything yet; counting it would score the period
        lower the earlier you look at it."""
        _permit(cost_center, END + timedelta(days=10))

        assert on_time_execution(START, END)["total"] == 0

    @pytest.mark.django_db
    def test_only_approved_or_completed_permits_count(self, cost_center):
        """A denied permit is not committed work that went unexecuted."""
        _permit(cost_center, date(2026, 8, 10), status="denied")
        _permit(cost_center, date(2026, 8, 11), status="requested")

        assert on_time_execution(START, END)["total"] == 0

    @pytest.mark.django_db
    def test_several_flights_on_one_permit_count_once(self, cost_center):
        """distinct(): the join would otherwise count the permit per flight and
        push the ratio over 100%."""
        permit = _permit(cost_center, date(2026, 8, 10))
        pilot = Operator.objects.create(employee_id="P1", full_name="Pilot One")
        aircraft = _aircraft("CC-A1")
        permit.operators.add(pilot)
        permit.aircraft_fleet.add(aircraft)
        for day in (8, 9):
            FlightRecord.objects.create(
                permission=permit,
                actual_date=date(2026, 8, day),
                departure_time=time(9, 0),
                arrival_time=time(10, 0),
                pilot=pilot,
                aircraft=aircraft,
            )

        result = on_time_execution(START, END)

        assert result["total"] == 1
        assert result["on_time"] == 1
        assert result["pct"] == 100.0

    @pytest.mark.django_db
    def test_no_closed_permits_gives_no_percentage(self, cost_center):
        assert on_time_execution(START, END)["pct"] is None


class TestTheReportSurface:
    @pytest.mark.django_db
    def test_availability_below_target_is_flagged(self, db):
        _aircraft("CC-A1")
        _aircraft("CC-A2", status="maintenance")  # 50%, under 90

        availability = operational_kpis(START, END)[0]

        assert availability["code"] == "fleet_availability"
        assert availability["met"] is False
        assert availability["detail"] == "1/2"

    @pytest.mark.django_db
    def test_availability_at_target_is_met(self, db):
        for index in range(10):
            _aircraft(f"CC-A{index}")

        assert operational_kpis(START, END)[0]["met"] is True

    @pytest.mark.django_db
    def test_an_indicator_without_a_target_is_never_a_miss(self, db):
        """On-time execution has no agreed target yet. Flagging it against an
        invented line is how a KPI becomes noise people learn to ignore."""
        cost_center = CostCenter.objects.create(code="CC1", name="Uno")
        _permit(cost_center, date(2026, 8, 10))  # 0%, unflown

        execution = operational_kpis(START, END)[1]

        assert execution["code"] == "on_time_execution"
        assert execution["value"] == 0.0
        assert execution["target"] is None
        assert execution["met"] is None

    @pytest.mark.django_db
    def test_the_report_page_renders_both(self, db):
        _aircraft("CC-A1")
        user = User.objects.create_user("reporter", password="pw")
        user.user_permissions.add(
            *Permission.objects.filter(codename__in=["view_document", "view_alert"])
        )
        client = Client()
        assert client.login(username="reporter", password="pw")

        response = client.get(reverse("compliance-report"))
        content = response.content.decode()

        assert response.status_code == 200
        assert len(response.context["report"]["operational_kpis"]) == 2
        assert "Disponibilidad de flota" in content
