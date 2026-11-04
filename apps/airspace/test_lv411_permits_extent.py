"""LV-411: la tarjeta «Espacio aéreo» dice QUÉ zona y QUÉ permiso, y el mapa dibuja la extensión real.

Se fija:

1. la tarjeta del panel nombra las zonas más cercanas con su faena con permiso, la distancia y dos
   enlaces (el mapa centrado en el par y la ficha del permiso), comparados contra `reverse` y los
   objetos; con más de tres, «y N más»; sin cruzar de empresa;
2. la capa de permisos del mapa entrega la geometría del plan geoespacial vinculado cuando existe
   (y la persona puede ver planes), el círculo cuando sólo hay radio, y `area="point"` cuando sólo hay
   un centro; un permiso sin coordenadas pero con plan se ubica en el centro del plan;
3. el listado (que arma el script con esa misma respuesta) no recibe nada que la persona no pueda ver:
   403 sin el permiso de modelo y aislamiento por empresa;
4. el script tiene el aviso «sin área», el listado y el enlace profundo `?permit=`.

Datos ficticios.
"""

import json
import re
import socket
import urllib.request
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone, translation

from apps.airspace.models import AirspaceFeature, AirspaceSnapshot
from apps.core.models import OperationalTenant
from apps.core.testing import login_as as _login_as
from apps.environment import airspace_near
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.geo.test_lv278_modalities import _circle, _closed_line, _document, _point
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

ROOT = Path(__file__).resolve().parents[2]
KML = Path(__file__).parent / "test_data" / "synthetic_airspace.kml"
JS = (ROOT / "static/js/airspace-map.js").read_text(encoding="utf-8")
AIR, PERMITS, PLANS = "view_airspacefeature", "view_flightpermission", "view_geoplan"
LAYERS = reverse("airspace-own-layers")
STRIP = reverse("environment-strip")
SANTIAGO = ("-33.4500", "-70.6600")  # SC-P30 y SC-R54 a menos de 10 km
D66 = ("-33.1900", "-70.4200")  # dentro de SC-D66; SC-R41 cerca
FAR = ("-23.6500", "-70.4000")  # nada cerca


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


@pytest.fixture(autouse=True)
def quiet(settings, monkeypatch):
    settings.WEATHER_ENABLED = False
    settings.WEATHER_DEFAULT_LABEL = ""
    settings.AIRSPACE_NEAR_KM = 10

    def refuse(*args, **kwargs):
        raise AssertionError("no se sale a la red")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def login_as(*codenames, member_of=None):
    client = _login_as(*codenames, member_of=member_of)
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "en"
    return client


@pytest.fixture
def snapshot(db):
    call_command("import_airspace_zones", "--file", str(KML), verbosity=0)
    return AirspaceSnapshot.objects.get(is_current=True)


@pytest.fixture
def tenants(db):
    return (
        OperationalTenant.objects.create(name="Mi empresa", slug="mi-empresa"),
        OperationalTenant.objects.create(name="Otra empresa", slug="otra-empresa"),
    )


def permit(tenant, code, coords, number=None, **extra):
    today = timezone.localdate()
    lat, lon = coords if coords else (None, None)
    center = CostCenter.objects.create(tenant=tenant, code=code, name=f"Faena {code}")
    data = {
        "internal_folio": f"F-{code}",
        "permission_number": number or f"P-{code}",
        "cost_center": center,
        "purpose": "patrol",
        "valid_from": today - timedelta(days=2),
        "valid_until": today + timedelta(days=20),
        "location": "x",
        "area_type": "unpopulated",
        "status": FlightPermission.STATUS_APPROVED,
        "latitude": lat,
        "longitude": lon,
    }
    data.update(extra)
    return FlightPermission.objects.create(**data)


def zone(code):
    return AirspaceFeature.objects.get(code=code, is_active=True)


def strip_cell(client):
    html = client.get(STRIP).content.decode()
    return html.split("env-cell--airspace")[1].split("</div>")[0]


# ── 1. la tarjeta nombra la zona y el permiso ────────────────────────────────


@pytest.mark.django_db
class TestTheCardNamesZoneAndPermit:
    def test_each_pair_carries_its_zone_its_permit_and_both_links(
        self, snapshot, tenants
    ):
        own = permit(tenants[0], "CC-A", SANTIAGO, number="7581")
        fact = airspace_near.airspace_near_fact(
            login_as(AIR, PERMITS, member_of=tenants[0]).user
        )
        assert fact["count"] == 2 and fact["more"] == 0
        by_code = {pair["code"]: pair for pair in fact["pairs"]}
        assert set(by_code) == {"SC-P30", "SC-R54"}
        p30 = by_code["SC-P30"]
        assert p30["zone_id"] == str(zone("SC-P30").pk)
        assert p30["name"] == zone("SC-P30").name
        assert p30["kind_label"] == str(
            dict(AirspaceFeature.KIND_CHOICES)["prohibited"]
        )
        assert p30["permit_number"] == "7581" and p30["permit_site"] == "CC-A"
        assert p30["permit_url"] == reverse("permission-detail", args=[own.pk])
        url = urlparse(p30["map_url"])
        assert url.path == reverse("airspace-map")
        assert parse_qs(url.query) == {
            "permit": [str(own.pk)],
            "layer": ["permits"],
            "zone": [str(zone("SC-P30").pk)],
        }
        # La más cercana primero; la distancia es desde el borde y nunca pasa del «cerca».
        distances = [pair["distance_km"] for pair in fact["pairs"]]
        assert distances == sorted(distances) and all(0 <= d <= 10 for d in distances)

    def test_the_card_draws_the_pairs_with_their_links(self, snapshot, tenants):
        own = permit(tenants[0], "CC-A", SANTIAGO, number="7581")
        cell = strip_cell(login_as(AIR, PERMITS, member_of=tenants[0]))
        assert 'class="env-air-pairs"' in cell
        assert f'href="{reverse("permission-detail", args=[own.pk])}"' in cell
        assert "Permit 7581" in cell
        assert f"permit={own.pk}" in cell and f"zone={zone('SC-R54').pk}" in cell
        assert "SC-P30 · " + zone("SC-P30").name in cell
        assert "Open the map" in cell

    def test_a_zone_inside_the_permit_area_says_it_touches_it(self, snapshot, tenants):
        permit(tenants[0], "CC-D", D66)
        client = login_as(AIR, PERMITS, member_of=tenants[0])
        fact = airspace_near.airspace_near_fact(client.user)
        d66 = next(pair for pair in fact["pairs"] if pair["code"] == "SC-D66")
        assert d66["distance_km"] == 0
        assert "touches the permit area of CC-D" in strip_cell(client)

    def test_more_than_three_shows_three_and_the_rest_as_a_count(
        self, snapshot, tenants
    ):
        permit(tenants[0], "CC-A", SANTIAGO)
        permit(tenants[0], "CC-D", D66)
        client = login_as(AIR, PERMITS, member_of=tenants[0])
        fact = airspace_near.airspace_near_fact(client.user)
        assert fact["count"] == 4
        assert len(fact["pairs"]) == airspace_near.PAIRS_SHOWN == 3
        assert fact["more"] == 1
        assert "and 1 more zone" in strip_cell(client)

    def test_another_companys_permit_is_never_named(self, snapshot, tenants):
        permit(tenants[0], "CC-MIO", FAR)
        theirs = permit(tenants[1], "CC-AJENO", SANTIAGO, number="9999")
        client = login_as(AIR, PERMITS, member_of=tenants[0])
        fact = airspace_near.airspace_near_fact(client.user)
        assert fact["pairs"] == [] and fact["count"] == 0
        cell = strip_cell(client)
        assert "9999" not in cell and str(theirs.pk) not in cell

    def test_the_pair_text_is_translated(self, snapshot, tenants):
        permit(tenants[0], "CC-A", SANTIAGO, number="7581")
        client = login_as(AIR, PERMITS, member_of=tenants[0])
        client.defaults["HTTP_ACCEPT_LANGUAGE"] = "es"
        with translation.override("es"):
            cell = strip_cell(client)
        assert "Permiso 7581" in cell and "Ver en el mapa" in cell
        assert "km del área del permiso de CC-A" in cell


# ── 2. el mapa entrega la extensión real ─────────────────────────────────────


@pytest.fixture
def author(db):
    return User.objects.create_user("autor-411", password="pw")  # nosec B106


def link_plan(flight_permit, author, document):
    plan = GeoPlan.objects.create(
        title="Plan ficticio",
        cost_center=flight_permit.cost_center,
        flight_permission=flight_permit,
        created_by=author,
    )
    version = GeoPlanVersion.objects.create(
        plan=plan,
        version_number=1,
        content=document,
        content_checksum="x" * 64,
        source="import",
        created_by=author,
    )
    plan.current_version = version
    plan.save(update_fields=["current_version", "updated_at"])
    return plan


def items(client, layer="permits"):
    return json.loads(client.get(f"{LAYERS}?layer={layer}").content)["items"]


@pytest.mark.django_db
class TestTheMapPayload:
    def test_a_linked_plan_travels_as_its_real_geometry(self, tenants, author):
        own = permit(tenants[0], "CC-A", SANTIAGO, radius_km="1.00")
        link_plan(own, author, _document(_circle("Area", 400), _point("Area", 0, 0)))
        (item,) = items(login_as(AIR, PERMITS, PLANS, member_of=tenants[0]))
        assert item["area"] == "plan"
        assert [g["type"] for g in item["geometries"]] == ["Polygon"]
        assert len(item["geometries"][0]["coordinates"][0]) == 65
        assert item["url"] == reverse("permission-detail", args=[own.pk])

    def test_a_trimble_closed_line_is_drawn_as_a_polygon(self, tenants, author):
        own = permit(tenants[0], "CC-A", SANTIAGO)
        ring = _circle("Area", 400)["geometry"]["coordinates"][0][:-1]
        link_plan(own, author, _document(_closed_line("Area", ring)))
        (item,) = items(login_as(AIR, PERMITS, PLANS, member_of=tenants[0]))
        assert [g["type"] for g in item["geometries"]] == ["Polygon"]

    def test_without_the_plan_permission_it_falls_back_to_the_circle(
        self, tenants, author
    ):
        own = permit(tenants[0], "CC-A", SANTIAGO, radius_km="1.00")
        link_plan(own, author, _document(_circle("Area", 400), _point("Area", 0, 0)))
        (item,) = items(login_as(AIR, PERMITS, member_of=tenants[0]))
        assert item["area"] == "circle" and item["geometries"] == []
        assert item["radius_km"] == pytest.approx(1.0)

    def test_a_radius_without_a_plan_is_a_circle(self, tenants):
        permit(tenants[0], "CC-A", SANTIAGO, radius_km="2.50")
        (item,) = items(login_as(AIR, PERMITS, PLANS, member_of=tenants[0]))
        assert item["area"] == "circle" and item["radius_km"] == pytest.approx(2.5)

    def test_only_a_centre_is_a_point_with_no_declared_area(self, tenants):
        permit(tenants[0], "CC-A", SANTIAGO, radius_km=None)
        (item,) = items(login_as(AIR, PERMITS, PLANS, member_of=tenants[0]))
        assert item["area"] == "point" and item["geometries"] == []

    def test_an_archived_plan_is_not_drawn(self, tenants, author):
        own = permit(tenants[0], "CC-A", SANTIAGO, radius_km=None)
        plan = link_plan(own, author, _document(_circle("Area", 400)))
        plan.is_active = False
        plan.save()
        (item,) = items(login_as(AIR, PERMITS, PLANS, member_of=tenants[0]))
        assert item["area"] == "point"

    def test_without_coordinates_a_plan_places_the_permit_at_its_centre(
        self, tenants, author
    ):
        own = permit(tenants[0], "CC-A", None)
        link_plan(own, author, _document(_circle("Area", 400), _point("Area", 0, 0)))
        client = login_as(AIR, PERMITS, PLANS, member_of=tenants[0])
        data = json.loads(client.get(f"{LAYERS}?layer=permits").content)
        (item,) = data["items"]
        assert item["area"] == "plan" and item["lat"] is not None
        assert data["unplaced"] == 0
        # Sin plan ni coordenadas no se dibuja, y se cuenta.
        permit(tenants[0], "CC-B", None)
        assert (
            json.loads(client.get(f"{LAYERS}?layer=permits").content)["unplaced"] == 1
        )

    def test_a_pending_permit_with_a_plan_also_travels_with_it(self, tenants, author):
        own = permit(
            tenants[0],
            "CC-A",
            SANTIAGO,
            status=FlightPermission.STATUS_REQUESTED,
            valid_from=None,
            valid_until=None,
        )
        link_plan(own, author, _document(_circle("Area", 400)))
        (item,) = items(login_as(AIR, PERMITS, PLANS, member_of=tenants[0]), "pending")
        assert item["area"] == "plan" and item["geometries"]


# ── 3. el listado no recibe lo que no se puede ver ───────────────────────────


@pytest.mark.django_db
class TestTheListIsGuarded:
    @pytest.mark.parametrize("layer", ["permits", "pending"])
    def test_without_the_permit_permission_it_is_403(self, tenants, layer):
        client = login_as(AIR, PLANS, member_of=tenants[0])
        assert client.get(f"{LAYERS}?layer={layer}").status_code == 403

    def test_another_companys_plan_geometry_never_travels(self, tenants, author):
        permit(tenants[0], "CC-MIO", SANTIAGO)
        theirs = permit(tenants[1], "CC-AJENO", D66)
        link_plan(theirs, author, _document(_circle("Ajena", 400)))
        client = login_as(AIR, PERMITS, PLANS, member_of=tenants[0])
        raw = client.get(f"{LAYERS}?layer=permits").content.decode()
        assert "CC-AJENO" not in raw and str(theirs.pk) not in raw
        assert [i["site"] for i in json.loads(raw)["items"]] == ["CC-MIO"]


# ── 4. el script ─────────────────────────────────────────────────────────────


class TestTheScript:
    SECTION = JS.split("capas propias (LV-358, E3)")[1].split("function buildLegend")[0]

    def test_a_point_without_area_says_so_and_looks_different(self):
        assert 'item.area === "point" ? title + " · " + T.noArea' in self.SECTION
        assert "air-own-noarea" in self.SECTION

    def test_the_plan_is_drawn_before_falling_back_to_the_circle(self):
        draw = self.SECTION.split("function drawPermit")[1].split("\n  function ")[0]
        assert draw.index("planShapes(") < draw.index("item.radius_km")

    def test_each_row_of_the_list_shows_and_opens_the_permit(self):
        rows = self.SECTION.split("function renderOwnList")[1].split("\n  function ")[0]
        assert "T.showOnMap" in rows and "T.openPermit" in rows
        assert "open.href = item.url" in rows and ".innerHTML" not in rows

    def test_the_deep_link_reads_permit_layer_and_zone(self):
        link = self.SECTION.split("function applyDeepLink")[1]
        assert all(
            f'params.get("{name}")' in link for name in ("permit", "layer", "zone")
        )
        assert re.search(r"applyDeepLink\(\);\s*\}", JS)
