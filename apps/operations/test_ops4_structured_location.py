"""OPS-4: structured location on FlightPermission (docs/dev/ops-contract-tracking-plan.md §1.4).

Complements the free-text `location` field with region/commune/area_name and
an optional coordinate pair + radius + max altitude, all optional.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.core.testing import login_as
from apps.registry.models import Aircraft, CostCenter, Operator

from .models import FlightPermission


def _cc(code="CC1"):
    return CostCenter.objects.create(code=code, name=code)


def _base_permission(cc, **extra):
    return FlightPermission.objects.create(
        permission_number="P-1",
        cost_center=cc,
        purpose="photogrammetry",  # R3.1 closed vocabulary
        valid_from=date(2026, 7, 1),
        valid_until=date(2026, 7, 10),
        location="Site",
        area_type="unpopulated",
        **extra,
    )


# The fields every permission form post needs regardless of what the test is
# actually exercising: R3.1 closed `purpose`, R2.6 `area_type`, LV-39 `status`.
_FORM_BASE = {
    "status": "requested",
    "permission_number": "P-1",
    "purpose": "photogrammetry",
    "valid_from": "2026-07-01",
    "valid_until": "2026-07-10",
    "location": "Site",
    "area_type": "unpopulated",
}


class TestStructuredLocationValidation:
    @pytest.mark.django_db
    def test_lone_latitude_is_rejected(self, db):
        cc = _cc()
        permission = _base_permission(cc, latitude=Decimal("-33.45"))
        with pytest.raises(ValidationError):
            permission.clean()

    @pytest.mark.django_db
    def test_lone_longitude_is_rejected(self, db):
        cc = _cc()
        permission = _base_permission(cc, longitude=Decimal("-70.66"))
        with pytest.raises(ValidationError):
            permission.clean()

    @pytest.mark.django_db
    def test_radius_without_coordinates_is_rejected(self, db):
        cc = _cc()
        permission = _base_permission(cc, radius_km=Decimal("2.5"))
        with pytest.raises(ValidationError):
            permission.clean()

    @pytest.mark.django_db
    def test_full_structured_location_is_accepted(self, db):
        cc = _cc()
        permission = _base_permission(
            cc,
            region="Antofagasta",
            commune="Calama",
            area_name="Mina Chuquicamata",
            latitude=Decimal("-22.298"),
            longitude=Decimal("-68.9"),
            radius_km=Decimal("1.5"),
            max_altitude_ft=400,
        )
        permission.clean()  # must not raise

    @pytest.mark.django_db
    def test_no_structured_location_is_accepted(self, db):
        cc = _cc()
        permission = _base_permission(cc)
        permission.clean()  # entirely optional -- must not raise


class TestStructuredLocationForm:
    @pytest.mark.django_db
    def test_create_form_rejects_lone_latitude(self, db):
        cc = _cc()
        operator = Operator.objects.create(employee_id="E1", full_name="Pilot")
        aircraft = Aircraft.objects.create(
            registration="CC-A1", type="RPA", model="M3", manufacturer="DJI"
        )
        client = login_as("add_flightpermission")

        response = client.post(
            reverse("permission-create"),
            _FORM_BASE
            | {
                "operators": [operator.pk],
                "aircraft_fleet": [aircraft.pk],
                "cost_center": cc.pk,
                "latitude": "-22.298",
            },
        )

        assert response.status_code == 200  # re-rendered with errors, not a redirect
        assert not FlightPermission.objects.filter(permission_number="P-1").exists()

    @pytest.mark.django_db
    def test_create_form_accepts_structured_location(self, db):
        cc = _cc()
        operator = Operator.objects.create(employee_id="E1", full_name="Pilot")
        aircraft = Aircraft.objects.create(
            registration="CC-A1", type="RPA", model="M3", manufacturer="DJI"
        )
        client = login_as("add_flightpermission")

        response = client.post(
            reverse("permission-create"),
            _FORM_BASE
            | {
                "operators": [operator.pk],
                "aircraft_fleet": [aircraft.pk],
                "cost_center": cc.pk,
                "region": "Antofagasta",
                "commune": "Calama",
                "area_name": "Mina Chuquicamata",
                "latitude": "-22.298",
                "longitude": "-68.9",
                "radius_km": "1.5",
                "max_altitude_ft": "400",
            },
        )

        assert response.status_code == 302
        permission = FlightPermission.objects.get(permission_number="P-1")
        assert permission.region == "Antofagasta"
        assert permission.max_altitude_ft == 400


class TestStructuredLocationDetailPage:
    @pytest.mark.django_db
    def test_renders_structured_location_when_present(self, db):
        cc = _cc()
        operator = Operator.objects.create(employee_id="E1", full_name="Pilot")
        aircraft = Aircraft.objects.create(
            registration="CC-A1", type="RPA", model="M3", manufacturer="DJI"
        )
        permission = _base_permission(
            cc,
            region="Antofagasta",
            commune="Calama",
            area_name="Mina Chuquicamata",
            latitude=Decimal("-22.298"),
            longitude=Decimal("-68.9"),
            radius_km=Decimal("1.5"),
            max_altitude_ft=400,
        )
        permission.operators.add(operator)
        permission.aircraft_fleet.add(aircraft)

        response = login_as("view_flightpermission").get(
            reverse("permission-detail", args=[permission.pk])
        )
        content = response.content.decode()

        assert response.status_code == 200
        assert "Mina Chuquicamata" in content
        assert "Antofagasta" in content
        assert "Calama" in content
        # Rendered under the Spanish locale: Django's decimal separator is a
        # comma here, not a period.
        assert "-22,298" in content
        assert "-68,9" in content
        assert "400" in content

    @pytest.mark.django_db
    def test_hides_structured_location_when_absent(self, db):
        cc = _cc()
        operator = Operator.objects.create(employee_id="E1", full_name="Pilot")
        aircraft = Aircraft.objects.create(
            registration="CC-A1", type="RPA", model="M3", manufacturer="DJI"
        )
        permission = _base_permission(cc)
        permission.operators.add(operator)
        permission.aircraft_fleet.add(aircraft)

        response = login_as("view_flightpermission").get(
            reverse("permission-detail", args=[permission.pk])
        )
        content = response.content.decode()

        assert response.status_code == 200
        assert "Region / Commune" not in content
        assert "Coordinates" not in content
        assert "Maximum altitude" not in content
