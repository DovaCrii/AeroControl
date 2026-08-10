"""R3.1: same closed vocabulary as FlightPermission (apps.core.choices), but
optional here -- LV-17 already decided purpose is a supplementary note on
an assignment, not a fact every assignment must carry."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .forms import OperatorAssignmentForm, OperatorBulkAssignForm
from .models import (
    Aircraft,
    AircraftAssignment,
    CostCenter,
    Operator,
    OperatorAssignment,
)


def _cc(code="CC1"):
    return CostCenter.objects.create(code=code, name=code)


def _operator(cc):
    return Operator.objects.create(employee_id="E1", full_name="Pilot", cost_center=cc)


def _aircraft(cc):
    return Aircraft.objects.create(
        registration="RPA-1",
        type="RPA",
        model="M300",
        manufacturer="DJI",
        cost_center=cc,
    )


@pytest.mark.django_db
def test_purpose_is_optional_on_operator_assignment():
    cc = _cc()
    assignment = OperatorAssignment(
        operator=_operator(cc), cost_center=cc, start_date=date(2026, 7, 1)
    )

    assignment.full_clean()  # must not raise: purpose left blank


@pytest.mark.django_db
def test_other_purpose_without_detail_fails_full_clean_on_operator_assignment():
    cc = _cc()
    assignment = OperatorAssignment(
        operator=_operator(cc),
        cost_center=cc,
        start_date=date(2026, 7, 1),
        purpose="other",
    )

    with pytest.raises(ValidationError) as excinfo:
        assignment.full_clean()

    assert "purpose_detail" in excinfo.value.message_dict


@pytest.mark.django_db
def test_database_constraint_rejects_other_without_detail_on_aircraft_assignment():
    cc = _cc()
    assignment = AircraftAssignment(
        aircraft=_aircraft(cc),
        cost_center=cc,
        start_date=date(2026, 7, 1),
        purpose="other",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            assignment.save()


@pytest.mark.django_db
def test_operator_assignment_form_requires_detail_when_other_selected():
    cc = _cc()
    data = {
        "operator": _operator(cc).pk,
        "cost_center": cc.pk,
        "status": "active",
        "purpose": "other",
        "purpose_detail": "",
    }

    form = OperatorAssignmentForm(data=data)

    assert not form.is_valid()
    assert "purpose_detail" in form.errors


@pytest.mark.django_db
def test_bulk_assign_form_requires_detail_when_other_selected():
    cc = _cc()
    data = {
        "cost_center": cc.pk,
        "operators": [_operator(cc).pk],
        "status": "active",
        "purpose": "other",
        "purpose_detail": "",
    }

    form = OperatorBulkAssignForm(data=data)

    assert not form.is_valid()
    assert "purpose_detail" in form.errors


@pytest.mark.django_db
def test_bulk_assign_form_leaves_purpose_optional():
    cc = _cc()
    data = {
        "cost_center": cc.pk,
        "operators": [_operator(cc).pk],
        "status": "active",
        "purpose": "",
        "purpose_detail": "",
    }

    form = OperatorBulkAssignForm(data=data)

    assert form.is_valid(), form.errors
