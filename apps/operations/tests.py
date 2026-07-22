from datetime import date, time

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.registry.models import Aircraft, CostCenter, Operator
from .forms import FlightRecordForm
from .models import FlightPermission


@pytest.mark.django_db
def test_flight_record_form_rejects_data_that_does_not_match_its_permission():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    other_operator = Operator.objects.create(
        employee_id="P2", full_name="Pilot Two", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    other_aircraft = Aircraft.objects.create(
        registration="CC-BBB",
        type="Fixed",
        model="B",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = FlightPermission.objects.create(
        permission_number="PERM-1",
        operator=operator,
        aircraft=aircraft,
        cost_center=cost_center,
        purpose="Training",
        flight_date=date(2026, 7, 22),
        location="Santiago",
    )

    form = FlightRecordForm(
        data={
            "permission": permission.pk,
            "actual_date": date(2026, 7, 23),
            "departure_time": time(10, 0),
            "arrival_time": time(9, 0),
            "pilot": other_operator.pk,
            "aircraft": other_aircraft.pk,
        }
    )

    assert not form.is_valid()
    assert {"actual_date", "arrival_time", "pilot", "aircraft"}.issubset(form.errors)


@pytest.mark.django_db
def test_permission_transition_requires_the_change_permission():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = FlightPermission.objects.create(
        permission_number="PERM-1",
        operator=operator,
        aircraft=aircraft,
        cost_center=cost_center,
        purpose="Training",
        flight_date=date(2026, 7, 22),
        location="Santiago",
    )
    User.objects.create_user("viewer", password="password")
    client = Client()
    assert client.login(username="viewer", password="password")

    response = client.post(reverse("permission-approve", args=[permission.pk]))

    assert response.status_code == 403
    permission.refresh_from_db()
    assert permission.status == "requested"
