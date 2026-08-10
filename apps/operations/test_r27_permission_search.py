"""R2.7: the search placeholder ("Search number, purpose, location...")
promised matches that `search_fields = ["permission_number"]` never
actually had. Depended on R3.1 landing first: the free-text purpose
column is `purpose_detail` now, not the (closed-choice) `purpose` field
itself."""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.registry.models import CostCenter

from .models import FlightPermission


def _permission(cost_center, **kwargs):
    kwargs.setdefault("purpose", "photogrammetry")
    kwargs.setdefault("valid_from", date(2026, 7, 22))
    kwargs.setdefault("valid_until", kwargs["valid_from"])
    kwargs.setdefault("location", "Santiago")
    kwargs.setdefault("area_type", "populated")
    return FlightPermission.objects.create(cost_center=cost_center, **kwargs)


@pytest.fixture
def admin_client(db):
    User.objects.create_superuser("admin", "admin@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client


@pytest.mark.django_db
def test_search_matches_purpose_detail(admin_client):
    cc = CostCenter.objects.create(code="CC1")
    match = _permission(cc, purpose_detail="Aerial corridor survey")
    other = _permission(cc, purpose_detail="Unrelated")

    response = admin_client.get(reverse("permission-list"), {"q": "corridor"})

    ids = {p.pk for p in response.context["objects"]}
    assert ids == {match.pk}
    assert other.pk not in ids


@pytest.mark.django_db
def test_search_matches_location(admin_client):
    cc = CostCenter.objects.create(code="CC1")
    match = _permission(cc, location="Valparaiso port")
    other = _permission(cc, location="Santiago")

    response = admin_client.get(reverse("permission-list"), {"q": "valparaiso"})

    ids = {p.pk for p in response.context["objects"]}
    assert ids == {match.pk}
    assert other.pk not in ids


@pytest.mark.django_db
def test_search_still_matches_internal_folio(admin_client):
    cc = CostCenter.objects.create(code="CC1")
    permission = _permission(cc)

    response = admin_client.get(
        reverse("permission-list"), {"q": permission.internal_folio}
    )

    assert {p.pk for p in response.context["objects"]} == {permission.pk}
