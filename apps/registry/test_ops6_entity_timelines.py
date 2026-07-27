"""OPS-6: each entity gets its own movement timeline, not one mixed list."""

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.registry.models import (
    Aircraft,
    AircraftAssignment,
    CostCenter,
    Operator,
    OperatorAssignment,
)

TODAY = timezone.localdate()


def _client(*codenames):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


class TestOperatorTimeline:
    @pytest.mark.django_db
    def test_hidden_without_permission(self, db):
        operator = Operator.objects.create(employee_id="E1", full_name="Pilot")
        response = _client("view_operator").get(
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

        response = _client("view_operator", "view_resourcemovementlog").get(
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
        response = _client("view_aircraft").get(
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

        response = _client("view_aircraft", "view_resourcemovementlog").get(
            reverse("aircraft-detail", args=[aircraft.pk])
        )

        movements = response.context["movements"]
        kinds = {entry.movement for entry in movements}
        # Both OPS-1's assignment-driven "assigned" and OPS-3's
        # "location_changed" land in the same timeline for this aircraft.
        assert "assigned" in kinds
        assert "location_changed" in kinds
