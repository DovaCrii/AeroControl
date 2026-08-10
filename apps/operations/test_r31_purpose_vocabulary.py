"""R3.1: `purpose` is a closed vocabulary now (apps.core.choices), not free
text -- confirmed against real data (R3.1a) and the user directly: the two
SIGO procedures under DAN 137 Cap. J are "Fotogrametría" and "Videos", not
"Videografía". "Other" exists because every real historical value mixed
more than one concept and none is a clean single-procedure match."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.registry.models import Aircraft, CostCenter, Operator

from .forms import FlightPermissionForm
from .models import FlightPermission


def _cc():
    return CostCenter.objects.create(code="OPS", name="Operations")


def _permission_kwargs(cost_center, **overrides):
    kwargs = {
        "cost_center": cost_center,
        "purpose": "photogrammetry",
        "valid_from": date(2026, 7, 22),
        "valid_until": date(2026, 7, 22),
        "location": "Santiago",
        "area_type": "populated",
    }
    kwargs.update(overrides)
    return kwargs


@pytest.mark.django_db
def test_purpose_choices_are_exactly_the_two_sigo_procedures_plus_other():
    codes = [
        code for code, _label in FlightPermission._meta.get_field("purpose").choices
    ]
    assert codes == ["photogrammetry", "video", "other"]


@pytest.mark.django_db
def test_other_purpose_without_detail_fails_full_clean():
    permission = FlightPermission(**_permission_kwargs(_cc(), purpose="other"))

    with pytest.raises(ValidationError) as excinfo:
        permission.full_clean()

    assert "purpose_detail" in excinfo.value.message_dict


@pytest.mark.django_db
def test_other_purpose_with_detail_saves_successfully():
    permission = FlightPermission(
        **_permission_kwargs(_cc(), purpose="other", purpose_detail="Aerial survey")
    )

    permission.full_clean()
    permission.save()

    assert permission.purpose_detail == "Aerial survey"


@pytest.mark.django_db
def test_database_constraint_rejects_other_without_detail_even_bypassing_clean():
    """The CheckConstraint is the real guard -- clean() alone would not stop
    a script or the admin from saving "other" with no detail."""
    permission = FlightPermission(**_permission_kwargs(_cc(), purpose="other"))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            permission.save()


@pytest.mark.django_db
def test_form_requires_detail_when_other_is_selected():
    cost_center = _cc()
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
    data = {
        "status": "requested",
        "operators": [operator.pk],
        "aircraft_fleet": [aircraft.pk],
        "cost_center": cost_center.pk,
        "purpose": "other",
        "purpose_detail": "",
        "valid_from": "2026-07-22",
        "valid_until": "2026-07-22",
        "location": "Santiago",
        "area_type": "populated",
    }

    form = FlightPermissionForm(data=data)

    assert not form.is_valid()
    assert "purpose_detail" in form.errors


@pytest.mark.django_db
def test_purpose_legacy_is_not_a_form_field():
    """Immutable historical record -- offering it on the form would let
    someone edit away the original SIGO wording the R3.1 backfill kept."""
    assert "purpose_legacy" not in FlightPermissionForm.Meta.fields
