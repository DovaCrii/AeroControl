"""R7.7: the five operational KPIs the guide asks for (ISO 9001 9.1.1).

The clause wants a target, a trend and action when the target is missed. These
cover value and target; the trend for document counters comes from
ComplianceSnapshot, already built.

Three of the five became computable only once R7.4 (`Deliverable`) and R7.6
(`NonConformity`) existed.
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


class TestSurveyAccuracy:
    @pytest.mark.django_db
    def test_only_assessable_deliverables_count(self, db):
        """A deliverable whose contract set no thresholds is neither a pass nor
        a failure. Folding it either way would make the number describe how
        many contracts have criteria, not how good the work was."""
        from decimal import Decimal

        from apps.compliance.kpis import survey_accuracy
        from apps.compliance.models import Deliverable

        with_criteria = CostCenter.objects.create(
            code="CC1", name="Uno", max_rmse_xy_cm=Decimal("10.0")
        )
        without = CostCenter.objects.create(code="CC2", name="Dos")
        passing = Deliverable.objects.create(
            title="Cumple", cost_center=with_criteria, rmse_xy_cm=Decimal("5.0")
        )
        failing = Deliverable.objects.create(
            title="No cumple", cost_center=with_criteria, rmse_xy_cm=Decimal("30.0")
        )
        unassessable = Deliverable.objects.create(
            title="Sin criterios", cost_center=without, rmse_xy_cm=Decimal("99.0")
        )
        for deliverable in (passing, failing, unassessable):
            deliverable.validate_quality(user=None)

        result = survey_accuracy(START, END)

        assert result["total"] == 2  # the unassessable one is out
        assert result["met"] == 1
        assert result["pct"] == 50.0

    @pytest.mark.django_db
    def test_nothing_validated_gives_no_percentage(self, db):
        from apps.compliance.kpis import survey_accuracy

        assert survey_accuracy(START, END)["pct"] is None


class TestReflightRate:
    @pytest.mark.django_db
    def test_counts_reflights_over_flights_flown(self, db):
        from apps.compliance.kpis import reflight_rate
        from apps.compliance.models import NonConformity

        cost_center = CostCenter.objects.create(code="CC1", name="Uno")
        permit = _permit(cost_center, date(2026, 8, 10))
        pilot = Operator.objects.create(employee_id="P1", full_name="Pilot One")
        aircraft = _aircraft("CC-A1")
        permit.operators.add(pilot)
        permit.aircraft_fleet.add(aircraft)
        for day in (5, 6, 7, 8):
            FlightRecord.objects.create(
                permission=permit,
                actual_date=date(2026, 8, day),
                departure_time=time(9, 0),
                arrival_time=time(10, 0),
                pilot=pilot,
                aircraft=aircraft,
            )
        NonConformity.objects.create(
            title="Re-vuelo",
            source=NonConformity.SOURCE_REFLIGHT,
            description="x",
            detected_on=date(2026, 8, 9),
        )

        result = reflight_rate(START, END)

        assert result["flights"] == 4
        assert result["reflights"] == 1
        assert result["pct"] == 25.0

    @pytest.mark.django_db
    def test_lower_is_better_so_the_direction_is_explicit(self, db):
        """Leaving the direction to be inferred from the name is how a red
        badge lands on the best month of the year."""
        from apps.compliance.kpis import LOWER_IS_BETTER, operational_kpis

        reflights = next(
            kpi
            for kpi in operational_kpis(START, END)
            if kpi["code"] == "reflight_rate"
        )

        assert reflights["direction"] == LOWER_IS_BETTER

    @pytest.mark.django_db
    def test_no_flights_gives_no_rate(self, db):
        from apps.compliance.kpis import reflight_rate

        assert reflight_rate(START, END)["pct"] is None


class TestIncidentFreeFlightHours:
    def _flight(self, permit, pilot, aircraft, day, hours=2):
        return FlightRecord.objects.create(
            permission=permit,
            actual_date=day,
            departure_time=time(9, 0),
            arrival_time=time(9 + hours, 0),
            pilot=pilot,
            aircraft=aircraft,
        )

    @pytest.mark.django_db
    def test_counts_the_whole_history_with_no_incident(self, db):
        from apps.compliance.kpis import incident_free_flight_hours

        cost_center = CostCenter.objects.create(code="CC1", name="Uno")
        permit = _permit(cost_center, date(2026, 8, 20))
        pilot = Operator.objects.create(employee_id="P1", full_name="Pilot One")
        aircraft = _aircraft("CC-A1")
        permit.operators.add(pilot)
        permit.aircraft_fleet.add(aircraft)
        self._flight(permit, pilot, aircraft, date(2026, 8, 5))
        self._flight(permit, pilot, aircraft, date(2026, 8, 6))

        result = incident_free_flight_hours()

        assert result["since"] is None
        assert result["hours"] == 4.0

    @pytest.mark.django_db
    def test_counts_only_after_the_last_incident(self, db):
        from apps.compliance.kpis import incident_free_flight_hours
        from apps.compliance.models import NonConformity

        cost_center = CostCenter.objects.create(code="CC1", name="Uno")
        permit = _permit(cost_center, date(2026, 8, 20))
        pilot = Operator.objects.create(employee_id="P1", full_name="Pilot One")
        aircraft = _aircraft("CC-A1")
        permit.operators.add(pilot)
        permit.aircraft_fleet.add(aircraft)
        self._flight(permit, pilot, aircraft, date(2026, 8, 5))  # before
        NonConformity.objects.create(
            title="Incidente",
            source=NonConformity.SOURCE_INCIDENT,
            description="x",
            detected_on=date(2026, 8, 6),
        )
        self._flight(permit, pilot, aircraft, date(2026, 8, 7), hours=3)  # after

        result = incident_free_flight_hours()

        assert result["since"] == date(2026, 8, 6)
        assert result["hours"] == 3.0

    @pytest.mark.django_db
    def test_a_flight_on_the_incident_day_does_not_count(self, db):
        """The counter runs from *after* the incident: a flight the same day
        happened around it, so claiming it as incident-free would overstate."""
        from apps.compliance.kpis import incident_free_flight_hours
        from apps.compliance.models import NonConformity

        cost_center = CostCenter.objects.create(code="CC1", name="Uno")
        permit = _permit(cost_center, date(2026, 8, 20))
        pilot = Operator.objects.create(employee_id="P1", full_name="Pilot One")
        aircraft = _aircraft("CC-A1")
        permit.operators.add(pilot)
        permit.aircraft_fleet.add(aircraft)
        NonConformity.objects.create(
            title="Incidente",
            source=NonConformity.SOURCE_INCIDENT,
            description="x",
            detected_on=date(2026, 8, 6),
        )
        self._flight(permit, pilot, aircraft, date(2026, 8, 6))

        assert incident_free_flight_hours()["hours"] == 0.0


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
    def test_all_five_indicators_the_guide_asks_for_are_present(self, db):
        """R7.4 and R7.6 unlocked the three that were missing, so 9.1.1's list
        is now complete."""
        codes = [kpi["code"] for kpi in operational_kpis(START, END)]

        assert codes == [
            "fleet_availability",
            "on_time_execution",
            "survey_accuracy",
            "reflight_rate",
            "incident_free_flight_hours",
        ]

    @pytest.mark.django_db
    def test_the_report_page_renders_them(self, db):
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
        assert len(response.context["report"]["operational_kpis"]) == 5
        assert "Disponibilidad de flota" in content
        assert "Tasa de re-vuelos" in content
        assert "Horas de vuelo sin incidentes" in content
        # A percentage with nothing to measure shows a dash, not its bare
        # "0/0" denominator -- the counter's unit is what tells them apart.
        assert "0/0" not in content
