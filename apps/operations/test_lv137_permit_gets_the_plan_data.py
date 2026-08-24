"""LV-137: el permiso recibe el AMC del plan, y el atajo vincula en vez de importar.

Textual del usuario, sobre el expediente operativo: *"el plan geoespacial no se
debe importar, se debe llamar desde el geoespacial que se crea dentro de la app, y
ese tiene además la información faltante para llenar el permiso, sobre todo el
tema de distancia punto central la distancia al aeródromo"*.

Dos defectos en una frase. **El atajo apuntaba a la puerta equivocada**: importar
crea un plan nuevo desde un KMZ, cuando el que hace falta ya existe y al
vincularlo rellena la ubicación del permiso. Y **el permiso no tenía dónde
guardar el aeródromo más cercano ni la distancia**: el plan los calculaba, la
solicitud SIGO los guardaba, y el permiso —la ficha donde se consulta el trámite—
los perdía.
"""

import math
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import reverse

from apps.core.testing import login_as
from apps.geo.kml.canonical import empty_document, new_uid
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.operations.dossier import operational_dossier
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = date(2026, 8, 24)
# Cerca de Quintero, que es el AMC que el catálogo de SIGO puede proponer.
LAT, LON = -32.5, -71.2


@pytest.fixture
def cost_center(db):
    call_command("seed_aerodromes")
    return CostCenter.objects.create(code="CC137", name="Faena")


@pytest.fixture
def owner(db):
    return User.objects.create_user("owner-137", "o137@test.com", "pw")  # nosec B106


@pytest.fixture
def permit(cost_center):
    return FlightPermission.objects.create(
        internal_folio="JEJ-2026-137",
        cost_center=cost_center,
        purpose="other",
        purpose_detail="Levantamiento",
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=30),
        location="Faena",
    )


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


def _one_circle_plan(cost_center, owner):
    """Un plan con **una** circunferencia: el caso donde el centro y el radio del
    permiso son los de esa circunferencia, sin ambigüedad."""
    ring = []
    for step in range(36):
        angle = 2 * math.pi * step / 36
        ring.append(
            [
                LON + (500 * math.sin(angle)) / (111_320 * math.cos(math.radians(LAT))),
                LAT + (500 * math.cos(angle)) / 111_320,
                0,
            ]
        )
    ring.append(list(ring[0]))
    document = empty_document()
    document["children"] = [
        _placemark("Punto central", {"type": "Point", "coordinates": [LON, LAT, 0]}),
        _placemark("Área", {"type": "Polygon", "coordinates": [ring]}),
    ]
    plan = GeoPlan.objects.create(
        title="Plan con una circunferencia",
        cost_center=cost_center,
        created_by=owner,
    )
    version = GeoPlanVersion.objects.create(
        plan=plan,
        version_number=1,
        content=document,
        content_checksum="x" * 64,
        source="import",
        created_by=owner,
    )
    plan.current_version = version
    plan.save(update_fields=["current_version", "updated_at"])
    return plan


@pytest.mark.django_db
class TestLinkingAPlanFillsTheAerodrome:
    def test_the_permit_had_nowhere_to_keep_it_and_now_does(self, permit):
        """El campo existe y arranca vacío: un permiso viejo sin AMC no es un
        permiso incompleto."""
        assert permit.amc is None
        assert permit.amc_distance_km is None

    def test_linking_fills_the_aerodrome_and_its_distance(
        self, permit, cost_center, owner
    ):
        plan = _one_circle_plan(cost_center, owner)

        response = login_as("change_geoplan", "view_flightpermission").post(
            reverse("permission-link-plan", args=[permit.pk]), {"plan": str(plan.pk)}
        )

        assert response.status_code == 302
        permit.refresh_from_db()
        assert permit.amc is not None
        assert permit.amc_distance_km is not None
        # Y la ubicación que ya rellenaba desde R10.2 sigue llegando.
        assert permit.latitude is not None
        assert permit.radius_km is not None

    def test_it_never_overwrites_an_aerodrome_already_on_the_permit(
        self, permit, cost_center, owner
    ):
        """Misma regla que las coordenadas: lo que el permiso ya trae manda,
        porque puede venir del papel DGAC."""
        from apps.registry.models import Aerodrome

        mine = Aerodrome.objects.create(
            code="SCXX", name="El del papel", latitude=LAT, longitude=LON
        )
        permit.amc = mine
        permit.amc_distance_km = Decimal("1.0")
        permit.save(update_fields=["amc", "amc_distance_km"])
        plan = _one_circle_plan(cost_center, owner)

        login_as("change_geoplan", "view_flightpermission").post(
            reverse("permission-link-plan", args=[permit.pk]), {"plan": str(plan.pk)}
        )

        permit.refresh_from_db()
        assert permit.amc == mine
        assert permit.amc_distance_km == Decimal("1.0")

    def test_the_pair_travels_together(self, permit):
        """Una distancia sin aeródromo no se puede leer, y un aeródromo sin
        distancia obliga a recalcularla para saber qué declarar."""
        filled = permit.fill_location_gaps(amc=None, amc_distance_km=Decimal("42.0"))

        assert "amc_distance_km" not in filled
        permit.refresh_from_db()
        assert permit.amc_distance_km is None


@pytest.mark.django_db
class TestTheDossierShortcut:
    def test_it_offers_to_link_when_there_is_a_plan_to_link(
        self, permit, cost_center, owner
    ):
        """Lo que el usuario corrigió: el plan que hace falta ya existe en la
        app, así que el atajo lleva al selector de vincular -- que además rellena
        el permiso -- y no a crear uno nuevo desde un KMZ."""
        GeoPlan.objects.create(
            title="Suelto en esta faena", cost_center=cost_center, created_by=owner
        )
        user = login_as("change_geoplan", "add_geoplan").user

        item = next(
            i for i in operational_dossier(permit, user)["items"] if i.key == "geo_plan"
        )

        assert item.action_url == "#tab-geo-plans"

    def test_it_falls_back_to_importing_when_there_is_nothing_to_link(
        self, permit, cost_center, owner
    ):
        """Sin planes sueltos en esta faena, importar es lo único que queda -- y
        ahí sí es la acción correcta."""
        otra_faena = CostCenter.objects.create(code="CC000", name="Otra")
        GeoPlan.objects.create(
            title="De otra faena", cost_center=otra_faena, created_by=owner
        )
        user = login_as("change_geoplan", "add_geoplan").user

        item = next(
            i for i in operational_dossier(permit, user)["items"] if i.key == "geo_plan"
        )

        assert item.action_url.startswith(reverse("geo-plan-import"))

    def test_a_plan_already_linked_to_another_permit_is_not_offered(
        self, permit, cost_center, owner
    ):
        """Reasignar un plan de un permiso a otro es un movimiento distinto
        (R10.2), así que no cuenta como "hay algo que vincular"."""
        otro = FlightPermission.objects.create(
            internal_folio="JEJ-2026-138",
            cost_center=cost_center,
            purpose="other",
            purpose_detail="Otro",
            valid_from=TODAY,
            valid_until=TODAY + timedelta(days=10),
            location="Faena",
        )
        GeoPlan.objects.create(
            title="Ya tomado",
            cost_center=cost_center,
            created_by=owner,
            flight_permission=otro,
        )
        user = login_as("change_geoplan", "add_geoplan").user

        item = next(
            i for i in operational_dossier(permit, user)["items"] if i.key == "geo_plan"
        )

        assert item.action_url.startswith(reverse("geo-plan-import"))
