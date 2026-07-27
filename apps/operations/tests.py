from datetime import date, time

import pytest
from django.contrib.auth.models import User
from django.db.models import ProtectedError
from django.test import Client
from django.urls import reverse

from apps.registry.models import Aircraft, CostCenter, Operator
from .forms import FlightRecordForm
from .models import FlightPermission, PermissionHistory


def _permission(cost_center, operator, aircraft, **kwargs):
    """A FlightPermission with the given operator/aircraft as its sole roster
    member (OPS-4: operators/aircraft_fleet are M2M, so they cannot be passed
    as .create() kwargs like the old single FKs could)."""
    kwargs.setdefault("permission_number", "PERM-1")
    kwargs.setdefault("purpose", "Training")
    kwargs.setdefault("valid_from", date(2026, 7, 22))
    kwargs.setdefault("valid_until", kwargs["valid_from"])
    kwargs.setdefault("location", "Santiago")
    permission = FlightPermission.objects.create(cost_center=cost_center, **kwargs)
    permission.operators.add(operator)
    permission.aircraft_fleet.add(aircraft)
    return permission


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
    permission = _permission(cost_center, operator, aircraft)

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
def test_flight_record_form_uses_operational_date_and_time_controls():
    form = FlightRecordForm()

    assert form.fields["actual_date"].widget.input_type == "date"
    assert form.fields["departure_time"].widget.input_type == "time"
    assert form.fields["arrival_time"].widget.input_type == "time"


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
    permission = _permission(cost_center, operator, aircraft)
    User.objects.create_user("viewer", password="password")
    client = Client()
    assert client.login(username="viewer", password="password")

    response = client.post(reverse("permission-approve", args=[permission.pk]))

    assert response.status_code == 403
    permission.refresh_from_db()
    assert permission.status == "requested"


@pytest.mark.django_db
def test_permission_transition_records_history_with_actor_and_notes():
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
    permission = _permission(cost_center, operator, aircraft)
    User.objects.create_superuser("dispatcher", "dispatcher@test.com", "password")
    client = Client()
    assert client.login(username="dispatcher", password="password")

    response = client.post(
        reverse("permission-approve", args=[permission.pk]),
        {"notes": "Approved after dispatch review."},
    )

    assert response.status_code == 302
    permission.refresh_from_db()
    history = PermissionHistory.objects.get(permission=permission)
    assert permission.status == "approved"
    assert history.previous_status == "requested"
    assert history.new_status == "approved"
    assert history.changed_by == "dispatcher"
    assert history.notes == "Approved after dispatch review."


@pytest.mark.django_db
def test_flight_permission_with_history_cannot_be_hard_deleted():
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
    permission = _permission(cost_center, operator, aircraft)
    PermissionHistory.objects.create(
        permission=permission,
        previous_status="requested",
        new_status="approved",
        changed_by="dispatcher",
    )

    with pytest.raises(ProtectedError):
        permission.delete()


@pytest.mark.django_db
def test_flight_record_form_allows_any_roster_operator_and_fleet_aircraft():
    """OPS-4: a permission's roster can be several operators/aircraft; a flight
    record is valid against any of them, not just "the" first one added."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator_one = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    operator_two = Operator.objects.create(
        employee_id="P2", full_name="Pilot Two", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(
        cost_center,
        operator_one,
        aircraft,
        valid_from=date(2026, 7, 20),
        valid_until=date(2026, 7, 25),
    )
    permission.operators.add(operator_two)

    form = FlightRecordForm(
        data={
            "permission": permission.pk,
            "actual_date": date(2026, 7, 23),  # inside the range, not the start
            "departure_time": time(9, 0),
            "arrival_time": time(10, 0),
            "pilot": operator_two.pk,  # the *second* operator, not the first
            "aircraft": aircraft.pk,
        }
    )

    assert form.is_valid(), form.errors
