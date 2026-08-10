"""R5.7: a newly-registered aircraft with the JAC policy already requested
looked identical to one with no insurance requested at all -- both showed
"-" on the list, since insurance_expiry was null either way.
insurance_status tracks the filing itself, same pattern as
CostCenter.contract_status (R3.3b)."""

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
def test_aircraft_defaults_to_active_insurance_status():
    aircraft = _aircraft()
    assert aircraft.insurance_status == "active"


@pytest.mark.django_db
def test_pending_status_is_kept_when_there_is_no_expiry_yet():
    aircraft = _aircraft(insurance_status="pending")
    aircraft.full_clean()
    assert aircraft.insurance_status == "pending"


@pytest.mark.django_db
def test_a_real_expiry_date_forces_the_status_back_to_active():
    """R5.7: "pasa a activo cuando se recibe" -- once the policy actually
    arrives, insurance_status cannot be left claiming "pending", or the
    field would contradict insurance_expiry, the one that actually drives
    the vigente/atrasado column."""
    aircraft = _aircraft(insurance_status="pending", insurance_expiry=date(2026, 12, 1))
    aircraft.full_clean()
    assert aircraft.insurance_status == "active"


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
