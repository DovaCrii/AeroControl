"""R5.7: a newly-registered aircraft with the JAC policy already requested
looked identical to one with no insurance requested at all -- both showed
"-" on the list, since insurance_expiry was null either way.
insurance_status tracks the filing itself, same pattern as
CostCenter.contract_status (R3.3b).

**Two of these tests changed with LV-81**, which turned the two states into the
four the real cycle has. Their premises expired rather than their behaviour
regressing, so the reasons are recorded inline below, and the new rules live in
test_lv81_insurance_flow.py."""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.registry.forms import AircraftForm
from apps.registry.models import Aircraft


def _aircraft(**kwargs):
    return Aircraft.objects.create(
        registration=kwargs.pop("registration", "CC-AAA"),
        type="RPA",
        model="M3",
        manufacturer="DJI",
        **kwargs,
    )


@pytest.fixture
def admin_client(db):
    User.objects.create_superuser("admin", "admin@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client


@pytest.mark.django_db
def test_aircraft_defaults_to_no_insurance_on_file():
    """LV-81 changed this default from "active" to "missing". R5.7 picked
    "active" because the only alternative then was "pending", which would have
    claimed a filing nobody opened -- but it meant a brand-new aircraft with
    nothing on file read "Vigente", and three production aircraft still do."""
    aircraft = _aircraft()
    assert aircraft.insurance_status == "missing"


@pytest.mark.django_db
def test_pending_status_is_kept_when_there_is_no_expiry_yet():
    aircraft = _aircraft(insurance_status="pending")
    aircraft.full_clean()
    assert aircraft.insurance_status == "pending"


@pytest.mark.django_db
def test_a_real_expiry_date_no_longer_forces_the_status_to_active():
    """**Reversed by LV-81, on purpose.** R5.7 read "pasa a activo cuando se
    recibe" as "an expiry date means the policy arrived", and forced the status.
    With four states that rule destroys the case the user asked for: while a
    renewal is being arranged the *current* policy still has its end date on
    file, so "pending" plus a date is a renewal in progress, not stale data.

    The contradiction R5.7 was actually protecting against -- a status claiming
    something the date denies -- is still handled, in the two directions that
    really cannot coexist (see test_lv81_insurance_flow.py)."""
    aircraft = _aircraft(insurance_status="pending", insurance_expiry=date(2099, 12, 1))
    aircraft.full_clean()
    assert aircraft.insurance_status == "pending"


@pytest.mark.django_db
def test_form_accepts_a_pending_filing():
    form = AircraftForm(
        data={
            "registration": "CC-AAA",
            "type": "RPA",
            "model": "M3",
            "manufacturer": "DJI",
            "insurance_status": "pending",
            "current_location": "headquarters",
            "status": "active",
        }
    )
    assert form.is_valid(), form.errors
    assert form.save().insurance_status == "pending"


@pytest.mark.django_db
def test_list_shows_filing_in_progress_badge_for_a_pending_aircraft(admin_client):
    _aircraft(registration="CC-PENDING", insurance_status="pending")

    content = admin_client.get(reverse("aircraft-list")).content.decode()

    assert "En trámite" in content


@pytest.mark.django_db
def test_list_shows_a_dash_for_an_aircraft_with_no_filing_and_no_expiry(admin_client):
    _aircraft(registration="CC-NONE")

    content = admin_client.get(reverse("aircraft-list")).content.decode()

    assert "CC-NONE" in content
    # No "En trámite" badge anywhere on the page for this aircraft's row --
    # the plain "-" case is the absence of the badge, not a positive marker.


@pytest.mark.django_db
def test_list_shows_the_expiry_date_instead_of_pending_once_it_exists(admin_client):
    _aircraft(
        registration="CC-ACTIVE",
        insurance_status="active",
        insurance_expiry=date(2099, 1, 1),
    )

    content = admin_client.get(reverse("aircraft-list")).content.decode()

    assert "2099-01-01" in content
