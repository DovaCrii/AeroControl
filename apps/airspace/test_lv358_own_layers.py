"""LV-358 (E3): las capas propias del mapa de espacio aéreo, «Mis faenas» y «Permisos vigentes».

Se fija: que cada capa pida SU permiso de modelo además del del mapa (403 por capa, LV-268), el
aislamiento entre tenants (fixture de dos tenants), qué entra en cada capa (faenas con coordenadas;
permisos aprobados y vigentes hoy), que la respuesta sea dato inerte (JSON escapado, `private`), que el
mapa sólo ofrezca a cada persona las capas de su permiso, que arranquen apagadas y se pidan recién al
encenderlas, y que el script dibuje con `textContent` y rótulos como nodos, con símbolo y texto.
"""

import json
import re
import socket
import urllib.request
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone, translation

from apps.airspace.models import AirspaceSnapshot
from apps.core.models import OperationalTenant
from apps.core.testing import login_as as _login_as
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

ROOT = Path(__file__).resolve().parents[2]
KML = Path(__file__).parent / "test_data" / "synthetic_airspace.kml"
JS = (ROOT / "static/js/airspace-map.js").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/airspace.css").read_text(encoding="utf-8")
AIR, SITES, PERMITS = "view_airspacefeature", "view_costcenter", "view_flightpermission"
LAYERS = reverse("airspace-own-layers")
PAGE = reverse("airspace-map")


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


@pytest.fixture(autouse=True)
def quiet(settings, monkeypatch):
    settings.WEATHER_ENABLED = False
    settings.WEATHER_DEFAULT_LABEL = ""

    def refuse(*args, **kwargs):
        raise AssertionError("las capas propias no pueden salir a la red")

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
def world(db):
    """Dos tenants, cada uno con una faena con coordenadas y un permiso vigente."""
    today = timezone.localdate()
    mine = OperationalTenant.objects.create(name="Mi empresa", slug="mi-empresa")
    other = OperationalTenant.objects.create(name="Otra empresa", slug="otra-empresa")
    data = {"mine": mine, "other": other}
    for key, tenant, lat, lon in (
        ("a", mine, "-33.4500", "-70.6600"),
        ("b", other, "-23.6500", "-70.4000"),
    ):
        center = CostCenter.objects.create(
            tenant=tenant,
            code=f"CC-{key.upper()}",
            name=f"Faena {key}",
            latitude=lat,
            longitude=lon,
        )
        permit = FlightPermission.objects.create(
            internal_folio=f"F-{key}",
            permission_number=f"P-{key}",
            cost_center=center,
            purpose="patrol",
            valid_from=today - timedelta(days=2),
            valid_until=today + timedelta(days=30),
            location=f"Lugar {key}",
            area_type="unpopulated",
            status=FlightPermission.STATUS_APPROVED,
            latitude=lat,
            longitude=lon,
            radius_km="1.50",
        )
        data[f"center_{key}"], data[f"permit_{key}"] = center, permit
    return data


def items(response):
    return json.loads(response.content)["items"]


# ── permisos (LV-268): el del mapa MÁS el de cada capa ────────────────────────


@pytest.mark.django_db
class TestPermissions:
    def test_each_layer_is_403_without_its_own_permission(self, world):
        only_map = login_as(AIR)
        assert only_map.get(LAYERS + "?layer=sites").status_code == 403
        assert only_map.get(LAYERS + "?layer=permits").status_code == 403

    def test_the_permit_permission_does_not_open_the_sites_layer_and_vice_versa(
        self, world
    ):
        permits_only = login_as(AIR, PERMITS)
        assert permits_only.get(LAYERS + "?layer=permits").status_code == 200
        assert permits_only.get(LAYERS + "?layer=sites").status_code == 403
        sites_only = login_as(AIR, SITES)
        assert sites_only.get(LAYERS + "?layer=sites").status_code == 200
        assert sites_only.get(LAYERS + "?layer=permits").status_code == 403

    @pytest.mark.parametrize("layer", ["sites", "permits"])
    def test_the_layer_permission_alone_is_not_enough_without_the_map_one(
        self, world, layer
    ):
        client = login_as(SITES, PERMITS)
        assert client.get(f"{LAYERS}?layer={layer}").status_code == 403

    def test_a_person_with_nothing_gets_403_and_an_anonymous_one_the_login(
        self, world, client
    ):
        assert login_as().get(LAYERS + "?layer=sites").status_code == 403
        response = client.get(LAYERS + "?layer=sites")
        assert response.status_code == 302 and "login" in response["Location"]

    def test_an_unknown_layer_is_a_400_and_a_missing_one_too(self, world):
        client = login_as(AIR, SITES, PERMITS)
        assert client.get(LAYERS + "?layer=weather").status_code == 400
        assert client.get(LAYERS).status_code == 400


# ── tenant ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTenantIsolation:
    def test_the_sites_layer_never_shows_another_tenants_site(self, world):
        client = login_as(AIR, SITES, member_of=world["mine"])
        codes = [item["code"] for item in items(client.get(LAYERS + "?layer=sites"))]
        assert codes == ["CC-A"]

    def test_the_permits_layer_never_shows_another_tenants_permit(self, world):
        client = login_as(AIR, PERMITS, member_of=world["mine"])
        numbers = [i["number"] for i in items(client.get(LAYERS + "?layer=permits"))]
        assert numbers == ["P-a"]

    def test_the_other_tenant_sees_its_own_and_only_its_own(self, world):
        client = login_as(AIR, SITES, PERMITS, member_of=world["other"])
        assert [i["code"] for i in items(client.get(LAYERS + "?layer=sites"))] == [
            "CC-B"
        ]
        assert [i["number"] for i in items(client.get(LAYERS + "?layer=permits"))] == [
            "P-b"
        ]

    def test_a_superuser_sees_both(self, world):
        client = login_as(AIR)
        client.user.is_superuser = True
        client.user.save()
        codes = {i["code"] for i in items(client.get(LAYERS + "?layer=sites"))}
        assert codes == {"CC-A", "CC-B"}


# ── qué entra en cada capa ───────────────────────────────────────────────────


@pytest.mark.django_db
class TestContent:
    def test_sites_need_coordinates_and_must_be_active(self, world):
        CostCenter.objects.create(tenant=world["mine"], code="CC-SIN", name="Sin coord")
        CostCenter.objects.create(
            tenant=world["mine"],
            code="CC-OFF",
            name="Archivada",
            latitude="-30",
            longitude="-70",
            is_active=False,
        )
        client = login_as(AIR, SITES, member_of=world["mine"])
        got = items(client.get(LAYERS + "?layer=sites"))
        assert [i["code"] for i in got] == ["CC-A"]
        assert got[0]["lat"] == pytest.approx(-33.45)
        assert got[0]["lon"] == pytest.approx(-70.66)

    def test_permits_must_be_approved_and_in_force_today(self, world):
        mine, today = world["mine"], timezone.localdate()
        center = world["center_a"]

        def permit(folio, **kwargs):
            data = {
                "internal_folio": folio,
                "cost_center": center,
                "purpose": "patrol",
                "valid_from": today - timedelta(days=2),
                "valid_until": today + timedelta(days=5),
                "location": "x",
                "area_type": "unpopulated",
                "status": FlightPermission.STATUS_APPROVED,
                "latitude": "-33.1",
                "longitude": "-70.1",
            }
            data.update(kwargs)
            return FlightPermission.objects.create(**data)

        permit("F-req", status=FlightPermission.STATUS_REQUESTED)
        permit("F-old", valid_until=today - timedelta(days=1))
        permit(
            "F-future",
            valid_from=today + timedelta(days=1),
            valid_until=today + timedelta(days=9),
        )
        permit("F-nocoord", latitude=None, longitude=None)
        permit("F-off", is_active=False)
        client = login_as(AIR, PERMITS, member_of=mine)
        got = items(client.get(LAYERS + "?layer=permits"))
        assert [i["number"] for i in got] == ["P-a"]
        assert got[0]["radius_km"] == pytest.approx(1.5)
        assert got[0]["site"] == "CC-A"
        assert got[0]["valid_until"] == (today + timedelta(days=30)).isoformat()

    def test_a_permit_without_radius_comes_as_a_point(self, world):
        permit = world["permit_a"]
        permit.radius_km = None
        permit.save()
        client = login_as(AIR, PERMITS, member_of=world["mine"])
        assert items(client.get(LAYERS + "?layer=permits"))[0]["radius_km"] is None


@pytest.mark.django_db
class TestTheResponseIsInertData:
    def test_it_is_json_private_and_markup_is_escaped(self, world):
        center = world["center_a"]
        center.name = "<script>alert(1)</script>&x"
        center.save()
        response = login_as(AIR, SITES, member_of=world["mine"]).get(
            LAYERS + "?layer=sites"
        )
        assert response["Content-Type"].startswith("application/json")
        assert "private" in response["Cache-Control"]
        raw = response.content.decode()
        assert "<script>" not in raw and "\\u003cscript\\u003e" in raw
        assert json.loads(raw)["items"][0]["name"] == "<script>alert(1)</script>&x"


# ── la pantalla ofrece sólo lo permitido, y apagado ──────────────────────────


def config_of(html):
    match = re.search(
        r'<script id="air-config" type="application/json">(.*?)</script>', html, re.S
    )
    return json.loads(match.group(1))


@pytest.mark.django_db
class TestTheScreen:
    def test_a_person_is_offered_only_the_layers_of_their_permissions(
        self, snapshot, world
    ):
        for codes, expected in (
            ((AIR,), []),
            ((AIR, SITES), ["sites"]),
            ((AIR, PERMITS), ["permits"]),
            ((AIR, SITES, PERMITS), ["sites", "permits"]),
        ):
            html = login_as(*codes, member_of=world["mine"]).get(PAGE).content.decode()
            assert [o["key"] for o in config_of(html)["ownLayers"]] == expected, codes

    def test_no_own_data_travels_in_the_page(self, snapshot, world):
        html = (
            login_as(AIR, SITES, PERMITS, member_of=world["mine"])
            .get(PAGE)
            .content.decode()
        )
        for private in ("CC-A", "P-a", "Faena a", "Lugar a", "-33.45"):
            assert private not in html.split('id="air-config"')[0], private
        config = json.dumps(config_of(html)["ownLayers"])
        assert "CC-A" not in config and "P-a" not in config
        assert all(
            o["url"].startswith(LAYERS + "?layer=")
            for o in config_of(html)["ownLayers"]
        )

    def test_the_strings_are_translated_in_the_config(self, snapshot, world):
        i18n = config_of(
            login_as(AIR, SITES, member_of=world["mine"]).get(PAGE).content.decode()
        )["i18n"]
        assert (
            i18n["layerSites"] == "My sites"
            and i18n["layerPermits"] == "Current permits"
        )
        with translation.override("es"):
            client = login_as(AIR, SITES, PERMITS, member_of=world["mine"])
            client.defaults["HTTP_ACCEPT_LANGUAGE"] = "es"
            es = config_of(client.get(PAGE).content.decode())["i18n"]
        assert (
            es["layerSites"] == "Mis faenas"
            and es["layerPermits"] == "Permisos vigentes"
        )


class TestTheScript:
    SECTION = JS.split("capas propias (LV-358, E3)")[1].split("function buildLegend")[0]

    def test_the_layers_start_off_and_load_only_when_switched_on(self):
        assert "box.checked = false;" in self.SECTION
        assert "loaded: false, on: false" in self.SECTION
        # Nada se pide al construir la leyenda: el `fetch` vive en `setOwnLayer`, al encender.
        assert self.SECTION.count("fetch(") == 1
        assert self.SECTION.index("function setOwnLayer") < self.SECTION.index("fetch(")

    def test_they_draw_with_text_content_and_nodes_never_with_inner_html(self):
        assert ".innerHTML" not in self.SECTION
        tooltips = re.findall(r"bindTooltip\(([^,)]+)", self.SECTION)
        assert tooltips and all(arg.startswith("tipNode(") for arg in tooltips)

    def test_each_layer_has_a_symbol_and_a_text_in_the_legend(self):
        assert '"■" : "◎"' in self.SECTION and "ownName(own.key)" in self.SECTION
        assert ".air-swatch--own-sites" in CSS and ".air-swatch--own-permits" in CSS

    def test_the_map_shapes_differ_besides_colour(self):
        # Cuadrado macizo = faena; círculo punteado = permiso vigente.
        assert (
            ".air-own-permit {" in CSS
            and "stroke-dasharray" in CSS.split(".air-own-permit {")[1].split("}")[0]
        )
        assert "air-own" in self.SECTION and "air-own-permit-dot" in self.SECTION
