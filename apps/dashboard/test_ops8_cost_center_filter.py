"""OPS-8: the dashboard's global cost-center filter."""

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator


@pytest.fixture
def auth_client(db):
    user = User.objects.create_user("dash-user", password="pw")
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


def _aircraft(cc, registration):
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3",
        manufacturer="DJI",
        cost_center=cc,
        status="active",
    )


@pytest.mark.django_db
def test_no_filter_counts_every_cost_center(auth_client):
    cc1 = CostCenter.objects.create(code="CC1", name="One")
    cc2 = CostCenter.objects.create(code="CC2", name="Two")
    _aircraft(cc1, "CC-A1")
    _aircraft(cc2, "CC-A2")

    response = auth_client.get(reverse("dashboard"))

    assert response.status_code == 200
    assert response.context["aircraft_count"] == 2
    assert response.context["selected_cost_center"] is None


@pytest.mark.django_db
def test_filter_narrows_aircraft_and_permission_counts(auth_client):
    cc1 = CostCenter.objects.create(code="CC1", name="One")
    cc2 = CostCenter.objects.create(code="CC2", name="Two")
    _aircraft(cc1, "CC-A1")
    aircraft2 = _aircraft(cc2, "CC-A2")
    operator = Operator.objects.create(employee_id="E1", full_name="Pilot")
    FlightPermission.objects.create(
        permission_number="P-1",
        operator=operator,
        aircraft=aircraft2,
        cost_center=cc2,
        purpose="Survey",
        flight_date="2026-01-01",
        location="Site",
    )

    response = auth_client.get(reverse("dashboard"), {"cost_center": cc2.pk})

    assert response.context["aircraft_count"] == 1
    assert response.context["selected_cost_center"] == cc2
    perms = {
        row["status"]: row["count"]
        for row in response.context["chart_data"]["permissions_by_status"]
    }
    assert sum(perms.values()) == 1


@pytest.mark.django_db
def test_unknown_cost_center_id_is_ignored(auth_client):
    cc1 = CostCenter.objects.create(code="CC1", name="One")
    _aircraft(cc1, "CC-A1")

    response = auth_client.get(reverse("dashboard"), {"cost_center": uuid.uuid4()})

    assert response.status_code == 200
    assert response.context["selected_cost_center"] is None
    assert response.context["aircraft_count"] == 1


@pytest.mark.django_db
def test_archived_cost_center_is_ignored(auth_client):
    cc1 = CostCenter.objects.create(code="CC1", name="One", is_active=False)
    _aircraft(cc1, "CC-A1")

    response = auth_client.get(reverse("dashboard"), {"cost_center": cc1.pk})

    assert response.context["selected_cost_center"] is None


@pytest.mark.django_db
def test_dropdown_lists_only_active_cost_centers(auth_client):
    CostCenter.objects.create(code="CC1", name="Active One")
    CostCenter.objects.create(code="CC2", name="Archived Two", is_active=False)

    response = auth_client.get(reverse("dashboard"))

    codes = {cc.code for cc in response.context["cost_centers"]}
    assert codes == {"CC1"}
