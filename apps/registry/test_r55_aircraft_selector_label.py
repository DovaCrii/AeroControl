"""R5.5: registration alone doesn't distinguish "which M300 is this" in a
dropdown with several of the same model -- absorbs LV-65."""

import pytest

from apps.registry.forms import (
    AircraftAssignmentForm,
    AircraftBulkAssignForm,
    AssignmentForm,
)
from apps.registry.models import Aircraft


def _aircraft(**kwargs):
    return Aircraft.objects.create(
        registration=kwargs.pop("registration", "CC-AAA"),
        type="RPA",
        model=kwargs.pop("model", "M300"),
        manufacturer="DJI",
        **kwargs,
    )


@pytest.mark.django_db
def test_selector_label_includes_model_and_serial():
    aircraft = _aircraft(registration="RPA-1", model="M300", serial_number="1ABC234")
    assert aircraft.selector_label == "RPA-1 · M300 · S/N 1ABC234"


@pytest.mark.django_db
def test_selector_label_omits_serial_when_blank():
    aircraft = _aircraft(registration="RPA-1", model="M300")
    assert aircraft.selector_label == "RPA-1 · M300"


@pytest.mark.django_db
def test_str_stays_just_the_registration():
    """__str__ is depended on elsewhere (movement logs, assignment tables)
    to stay short -- selector_label is deliberately a separate property."""
    aircraft = _aircraft(registration="RPA-1", model="M300", serial_number="1ABC234")
    assert str(aircraft) == "RPA-1"


@pytest.mark.django_db
def test_assignment_form_aircraft_field_uses_the_selector_label():
    aircraft = _aircraft(registration="RPA-1", model="M300", serial_number="1ABC234")
    form = AssignmentForm()
    assert form.fields["aircraft"].label_from_instance(aircraft) == (
        "RPA-1 · M300 · S/N 1ABC234"
    )


@pytest.mark.django_db
def test_aircraft_assignment_form_aircraft_field_uses_the_selector_label():
    aircraft = _aircraft(registration="RPA-1", model="M300", serial_number="1ABC234")
    form = AircraftAssignmentForm()
    assert form.fields["aircraft"].label_from_instance(aircraft) == (
        "RPA-1 · M300 · S/N 1ABC234"
    )


@pytest.mark.django_db
def test_aircraft_bulk_assign_form_aircraft_field_uses_the_selector_label():
    aircraft = _aircraft(registration="RPA-1", model="M300", serial_number="1ABC234")
    form = AircraftBulkAssignForm()
    assert form.fields["aircraft"].label_from_instance(aircraft) == (
        "RPA-1 · M300 · S/N 1ABC234"
    )
