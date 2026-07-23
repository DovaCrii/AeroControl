from datetime import date

import pytest
from django.urls import reverse

from apps.core.models import OperationalTenant
from apps.operations.models import FlightPermission
from apps.registry.forms import AssignmentForm
from apps.registry.models import Aircraft, Assignment, CostCenter, Operator, Qualification


@pytest.fixture
def admin_user(django_user_model):
    return django_user_model.objects.create_superuser(
        username="registry-admin", email="registry@example.com", password="password"
    )


@pytest.fixture
def registry_data():
    tenant = OperationalTenant.objects.create(name="Operations", slug="operations")
    center = CostCenter.objects.create(code="410", name="Operations", tenant=tenant)
    operator = Operator.objects.create(
        employee_id="OP-1", full_name="Pilot One", tenant=tenant, cost_center=center
    )
    aircraft = Aircraft.objects.create(
        registration="RPA-1",
        type="RPAS",
        model="Mavic 3",
        manufacturer="DJI",
        tenant=tenant,
        cost_center=center,
    )
    return tenant, center, operator, aircraft


@pytest.mark.django_db
def test_aircraft_list_exposes_model(client, admin_user, registry_data):
    client.force_login(admin_user)
    response = client.get(reverse("aircraft-list"))

    assert response.status_code == 200
    assert "RPA-1" in response.content.decode()
    assert "Mavic 3" in response.content.decode()


@pytest.mark.django_db
def test_confirmed_assignment_rejects_operator_overlap(registry_data):
    _tenant, center, operator, aircraft = registry_data
    Assignment.objects.create(
        operator=operator,
        aircraft=aircraft,
        cost_center=center,
        start_date=date(2026, 7, 10),
        end_date=date(2026, 7, 12),
        status="confirmed",
    )
    form = AssignmentForm(
        data={
            "operator": operator.pk,
            "aircraft": aircraft.pk,
            "cost_center": center.pk,
            "purpose": "Inspection",
            "start_date": "2026-07-11",
            "end_date": "2026-07-13",
            "status": "confirmed",
        }
    )

    assert not form.is_valid()
    assert "operator" in form.errors


@pytest.mark.django_db
def test_calendar_feed_contains_resource_and_expiration_events(client, admin_user, registry_data):
    _tenant, center, operator, aircraft = registry_data
    Assignment.objects.create(
        operator=operator,
        aircraft=aircraft,
        cost_center=center,
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 22),
        status="planned",
    )
    Qualification.objects.create(
        operator=operator,
        qualification_type="RPAS",
        issue_date=date(2026, 1, 1),
        expiry_date=date(2026, 7, 21),
    )
    FlightPermission.objects.create(
        permission_number="PERM-1",
        operator=operator,
        aircraft=aircraft,
        cost_center=center,
        purpose="Inspection",
        flight_date=date(2026, 7, 20),
        location="Santiago",
    )
    client.force_login(admin_user)

    response = client.get(
        reverse("calendar-events"),
        {"start": "2026-07-01", "end": "2026-08-01", "types": "permission,assignment,qualification"},
    )
    event_types = {event["type"] for event in response.json()}

    assert response.status_code == 200
    assert {"permission", "assignment", "qualification"}.issubset(event_types)
