"""LV-153: el permiso nuevo trae del plan las ocho casillas de geografía.

Textual del usuario, con la captura del formulario de alta en blanco: *"lo mismo,
el permiso de vuelo: estos datos debe extraerlos desde el KMZ, prepararlo y
dejarlo listo el KMZ para que saque esta información faltante"*.

La mitad existía y llegaba tarde: `R10.2`/`LV-137` rellenan esos huecos **al
vincular un plan**, pero eso ocurre en la ficha del permiso ya creado, así que al
darlo de alta las ocho casillas seguían en blanco y se tipeaban con el KMZ
delante.

Tres decisiones que estos tests fijan:

- Se elige un plan **ya subido**, no se sube un KMZ. La dirección la fijó el
  usuario en `LV-137`: *"el plan geoespacial no se debe importar, se debe llamar
  desde el geoespacial que se crea dentro de la app"*.
- El relleno ocurre **al guardar**. Recargar la página para rellenar habría
  borrado todo lo demás que la persona ya tipeó.
- Un plan alimenta un permiso **de su misma faena**, la regla que la puerta de la
  ficha ya aplicaba.
"""

import math

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.geo.kml.canonical import empty_document, new_uid
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.operations.forms import FlightPermissionForm, FlightPermissionUpdateForm
from apps.operations.models import FlightPermission
from apps.registry.models import Aerodrome, Aircraft, CostCenter, Operator

LAT, LON = -31.89439167, -70.70220833
TODAY = timezone.localdate()


def _ring(lat, lon, radius_m, vertices=36):
    ring = []
    for step in range(vertices):
        angle = 2 * math.pi * step / vertices
        dlat = (radius_m * math.cos(angle)) / 111_320
        dlon = (radius_m * math.sin(angle)) / (111_320 * math.cos(math.radians(lat)))
        ring.append([lon + dlon, lat + dlat, 0])
    ring.append(list(ring[0]))
    return ring


def _placemark(name, geometry):
    return {
        "kind": "placemark",
        "uid": new_uid("placemark"),
        "name": name,
        "description": "",
        "visibility": True,
        "style_url": None,
        "geometry": geometry,
        "extended_data": None,
        "extras": [],
    }


def _plan(cost_center, circles, *, title="Quebradas MLP"):
    author = User.objects.create_user(f"author-{new_uid('u')}", "a@test.com", "x")
    document = empty_document()
    for name, lat, lon, radius_m in circles:
        document["children"].append(
            _placemark(name, {"type": "Point", "coordinates": [lon, lat, 0]})
        )
        document["children"].append(
            _placemark(
                "", {"type": "Polygon", "coordinates": [_ring(lat, lon, radius_m)]}
            )
        )
    plan = GeoPlan.objects.create(
        title=title, cost_center=cost_center, created_by=author, status="draft"
    )
    version = GeoPlanVersion.objects.create(
        plan=plan,
        version_number=1,
        content=document,
        content_checksum="x" * 64,
        source="import",
        feature_count=len(circles) * 2,
        size_bytes=10,
        created_by=author,
    )
    plan.current_version = version
    plan.save(update_fields=["current_version", "updated_at"])
    return plan


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


@pytest.fixture
def aerodrome(db):
    return Aerodrome.objects.create(
        code="SCER", name="Ad. Militar Quintero", latitude=-32.7902, longitude=-71.5216
    )


def _payload(cost_center, **overrides):
    operator = Operator.objects.create(employee_id="E-1", full_name="Ana Rivas")
    aircraft = Aircraft.objects.create(
        registration="RPA-4883", type="Multirotor", model="M3E", manufacturer="DJI"
    )
    data = {
        "status": "requested",
        "permission_number": "",
        "operators": [operator.pk],
        "aircraft_fleet": [aircraft.pk],
        "cost_center": cost_center.pk,
        "purpose": "photogrammetry",
        "purpose_detail": "",
        "valid_from": TODAY.isoformat(),
        "valid_until": (TODAY + timezone.timedelta(days=30)).isoformat(),
        "location": "Quebradas STR MLP",
        "region": "",
        "commune": "",
        "area_name": "",
        "latitude": "",
        "longitude": "",
        "radius_km": "",
        "max_altitude_ft": "",
        "area_type": "unpopulated",
        "source_plan": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestTheCreateFormOffersTheAlreadyUploadedPlans:
    def test_an_unlinked_plan_is_offered(self, cost_center):
        plan = _plan(cost_center, [("Quebrada km 13.760", LAT, LON, 30)])

        offered = list(FlightPermissionForm().fields["source_plan"].queryset)

        assert offered == [plan]

    def test_a_plan_already_linked_to_another_permit_is_not_offered(self, cost_center):
        # Reasignar un plan es otro movimiento y tiene su propia puerta.
        plan = _plan(cost_center, [("Quebrada", LAT, LON, 30)])
        other = FlightPermission.objects.create(
            cost_center=cost_center,
            purpose="photogrammetry",
            area_type="unpopulated",
            valid_from=TODAY,
            valid_until=TODAY + timezone.timedelta(days=30),
        )
        plan.flight_permission = other
        plan.save(update_fields=["flight_permission"])

        assert not FlightPermissionForm().fields["source_plan"].queryset.exists()

    def test_an_archived_plan_is_not_offered(self, cost_center):
        plan = _plan(cost_center, [("Quebrada", LAT, LON, 30)])
        plan.is_active = False
        plan.save(update_fields=["is_active"])

        assert not FlightPermissionForm().fields["source_plan"].queryset.exists()

    def test_nothing_is_offered_without_permission_to_link_a_plan(self, cost_center):
        # Vincular modifica el plan: sin `geo.change_geoplan` el selector no se
        # ofrece, porque un enlace que termina en 403 enseña a desconfiar de la
        # pantalla (LV-130).
        _plan(cost_center, [("Quebrada", LAT, LON, 30)])
        user = login_as("add_flightpermission").user

        form = FlightPermissionForm(user=user)

        assert not form.fields["source_plan"].queryset.exists()

    def test_the_edit_form_does_not_offer_it(self, cost_center):
        permission = FlightPermission.objects.create(
            cost_center=cost_center,
            purpose="photogrammetry",
            area_type="unpopulated",
            valid_from=TODAY,
            valid_until=TODAY + timezone.timedelta(days=30),
        )

        assert (
            "source_plan" not in FlightPermissionUpdateForm(instance=permission).fields
        )


@pytest.mark.django_db
class TestSavingFillsTheEmptyBoxes:
    def test_the_plan_fills_the_location_block(self, cost_center, aerodrome):
        plan = _plan(cost_center, [("Quebrada km 13.760", LAT, LON, 30)])
        client = login_as("add_flightpermission", "change_geoplan")

        response = client.post(
            reverse("permission-create"),
            _payload(cost_center, source_plan=plan.pk),
        )
        permission = FlightPermission.objects.get(cost_center=cost_center)

        assert response.status_code == 302
        assert permission.latitude is not None
        assert permission.longitude is not None
        assert permission.radius_km is not None
        assert permission.commune
        assert permission.region
        assert permission.amc == aerodrome
        assert permission.amc_distance_km is not None

    def test_the_plan_is_linked_to_the_new_permit(self, cost_center, aerodrome):
        plan = _plan(cost_center, [("Quebrada", LAT, LON, 30)])
        client = login_as("add_flightpermission", "change_geoplan")

        client.post(
            reverse("permission-create"), _payload(cost_center, source_plan=plan.pk)
        )
        plan.refresh_from_db()

        assert plan.flight_permission == FlightPermission.objects.get(
            cost_center=cost_center
        )

    def test_what_the_person_typed_is_not_overwritten(self, cost_center, aerodrome):
        # `fill_location_gaps` rellena huecos, no pisa: si alguien escribió la
        # comuna a mano, gana lo que escribió.
        plan = _plan(cost_center, [("Quebrada", LAT, LON, 30)])
        client = login_as("add_flightpermission", "change_geoplan")

        client.post(
            reverse("permission-create"),
            _payload(cost_center, source_plan=plan.pk, commune="Salamanca"),
        )
        permission = FlightPermission.objects.get(cost_center=cost_center)

        assert permission.commune == "Salamanca"

    def test_a_permit_without_a_plan_saves_as_before(self, cost_center):
        client = login_as("add_flightpermission", "change_geoplan")

        response = client.post(reverse("permission-create"), _payload(cost_center))

        assert response.status_code == 302
        assert FlightPermission.objects.get(cost_center=cost_center).latitude is None


@pytest.mark.django_db
class TestAPlanOnlyFeedsItsOwnCostCenter:
    def test_a_plan_from_another_cost_center_is_rejected(self, cost_center):
        other = CostCenter.objects.create(code="CC861", name="Talabre")
        plan = _plan(other, [("Quebrada", LAT, LON, 30)])

        form = FlightPermissionForm(data=_payload(cost_center, source_plan=plan.pk))

        assert not form.is_valid()
        assert "source_plan" in form.errors
        assert "CC861" in form.errors["source_plan"][0]
