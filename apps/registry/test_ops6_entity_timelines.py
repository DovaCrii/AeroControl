"""OPS-6: each entity gets its own movement timeline, not one mixed list."""

from datetime import date, time

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.registry.models import (
    Aircraft,
    AircraftAssignment,
    CostCenter,
    Operator,
    OperatorAssignment,
)

TODAY = timezone.localdate()


class TestOperatorTimeline:
    @pytest.mark.django_db
    def test_hidden_without_permission(self, db):
        operator = Operator.objects.create(employee_id="E1", full_name="Pilot")
        response = login_as("view_operator").get(
            reverse("operator-detail", args=[operator.pk])
        )
        assert response.context["movements"] is None

    @pytest.mark.django_db
    def test_shows_only_this_operators_movements(self, db):
        cc1, cc2 = (
            CostCenter.objects.create(code="CC1", name="One"),
            CostCenter.objects.create(code="CC2", name="Two"),
        )
        operator = Operator.objects.create(employee_id="E1", full_name="Pilot One")
        other = Operator.objects.create(employee_id="E2", full_name="Pilot Two")
        OperatorAssignment.objects.create(
            operator=operator, cost_center=cc1, start_date=TODAY, status="active"
        )
        # A movement for a DIFFERENT operator must not leak into this timeline.
        OperatorAssignment.objects.create(
            operator=other, cost_center=cc2, start_date=TODAY, status="active"
        )

        response = login_as("view_operator", "view_resourcemovementlog").get(
            reverse("operator-detail", args=[operator.pk])
        )

        movements = response.context["movements"]
        assert len(movements) == 1
        assert movements[0].resource_id == operator.pk
        assert "Pilot Two" not in response.content.decode()


class TestAircraftTimeline:
    @pytest.mark.django_db
    def test_hidden_without_permission(self, db):
        aircraft = Aircraft.objects.create(
            registration="CC-A1", type="RPA", model="M3", manufacturer="DJI"
        )
        response = login_as("view_aircraft").get(
            reverse("aircraft-detail", args=[aircraft.pk])
        )
        assert response.context["movements"] is None

    @pytest.mark.django_db
    def test_combines_assignment_and_location_movements(self, db):
        cc = CostCenter.objects.create(code="CC1", name="One")
        aircraft = Aircraft.objects.create(
            registration="CC-A1", type="RPA", model="M3", manufacturer="DJI"
        )
        AircraftAssignment.objects.create(
            aircraft=aircraft, cost_center=cc, start_date=TODAY, status="active"
        )
        aircraft.current_location = "on_site"
        aircraft.current_site = cc
        aircraft.save(update_fields=["current_location", "current_site", "updated_at"])

        response = login_as("view_aircraft", "view_resourcemovementlog").get(
            reverse("aircraft-detail", args=[aircraft.pk])
        )

        movements = response.context["movements"]
        kinds = {entry.movement for entry in movements}
        # Both OPS-1's assignment-driven "assigned" and OPS-3's
        # "location_changed" land in the same timeline for this aircraft.
        assert "assigned" in kinds
        assert "location_changed" in kinds


class TestAircraftMaintenanceHistory:
    """R5.4: the fiche's maintenance history is the completed side of the
    same record set open_maintenance already shows -- so an open record does
    not appear twice on the same page."""

    @pytest.mark.django_db
    def test_hidden_without_permission(self, db):
        aircraft = Aircraft.objects.create(
            registration="CC-A1", type="RPA", model="M3", manufacturer="DJI"
        )
        response = login_as("view_aircraft").get(
            reverse("aircraft-detail", args=[aircraft.pk])
        )
        assert response.context["open_maintenance"] is None
        assert response.context["maintenance_history"] is None

    @pytest.mark.django_db
    def test_separates_open_from_completed(self, db):
        from apps.maintenance.models import MaintenanceRecord

        aircraft = Aircraft.objects.create(
            registration="CC-A1", type="RPA", model="M3", manufacturer="DJI"
        )
        open_record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="scheduled",
            description="Revisión anual",
            status="pending",
        )
        completed_record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="scheduled",
            description="Cambio de hélices",
            status="completed",
            completed_date=TODAY,
            performed_by="Taller JEJ",
        )

        response = login_as("view_aircraft", "view_maintenancerecord").get(
            reverse("aircraft-detail", args=[aircraft.pk])
        )

        open_ids = {m.pk for m in response.context["open_maintenance"]}
        history_ids = {m.pk for m in response.context["maintenance_history"]}
        assert open_ids == {open_record.pk}
        assert history_ids == {completed_record.pk}


class TestAircraftFlightHours:
    """R5.4/R7.1: cumulative flight time on the fiche."""

    def _aircraft_with_records(self, *spans):
        from apps.operations.models import FlightPermission, FlightRecord

        cc = CostCenter.objects.create(code="CC1", name="One")
        operator = Operator.objects.create(employee_id="E1", full_name="Pilot One")
        aircraft = Aircraft.objects.create(
            registration="CC-A1", type="RPA", model="M3", manufacturer="DJI"
        )
        permission = FlightPermission.objects.create(
            cost_center=cc,
            purpose="photogrammetry",
            valid_from=date(2026, 7, 22),
            valid_until=date(2026, 7, 22),
            location="Santiago",
        )
        permission.operators.add(operator)
        permission.aircraft_fleet.add(aircraft)
        for departure, arrival in spans:
            FlightRecord.objects.create(
                permission=permission,
                actual_date=date(2026, 7, 22),
                departure_time=departure,
                arrival_time=arrival,
                pilot=operator,
                aircraft=aircraft,
            )
        return aircraft

    @pytest.mark.django_db
    def test_hidden_without_permission(self, db):
        aircraft = self._aircraft_with_records((time(9, 0), time(10, 0)))
        response = login_as("view_aircraft").get(
            reverse("aircraft-detail", args=[aircraft.pk])
        )
        assert response.context["total_flight_hours"] is None

    @pytest.mark.django_db
    def test_sums_every_flight_for_this_aircraft(self, db):
        aircraft = self._aircraft_with_records(
            (time(9, 0), time(10, 30)),  # 1h30
            (time(11, 0), time(11, 45)),  # 45min
        )

        response = login_as("view_aircraft", "view_flightrecord").get(
            reverse("aircraft-detail", args=[aircraft.pk])
        )

        assert response.context["total_flight_hours"] == "2h 15min"
