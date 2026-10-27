"""LV-379: la capa «Permisos en trámite» del mapa de espacio aéreo.

Se fija: que sea una capa APARTE de «Permisos vigentes» (`?layer=pending`) con el mismo permiso de modelo
(403 sin él y no se ofrece), que sólo entren los permisos «Solicitados» y activos, que sólo viajen los que
tienen ubicación (los demás suman a `unplaced`, sin usar la faena de respaldo), que un permiso en trámite
sin folio de la DGAC ni fechas no rompa la respuesta, el aislamiento por empresa, que no viajen operadores
ni matrículas, y que el script cree su panel bajo el halo, arranque apagado y dibuje con `textContent`.
"""

# ruff: noqa: F811
import json
import re
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.airspace.test_lv358_own_layers import (  # noqa: F401  (fixtures compartidas)
    AIR,
    LAYERS,
    PAGE,
    PERMITS,
    SITES,
    config_of,
    english,
    items,
    login_as,
    quiet,
    snapshot,
    world,
)
from apps.operations.models import FlightPermission

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "static/css/airspace.css").read_text(encoding="utf-8")
JS = (ROOT / "static/js/airspace-map.js").read_text(encoding="utf-8")
NODE = shutil.which("node")
PENDING = LAYERS + "?layer=pending"


def payload_of(response):
    return json.loads(response.content)


def requested(world, folio, **kwargs):
    data = {
        "internal_folio": folio,
        "cost_center": world["center_a"],
        "purpose": "patrol",
        "location": "Lugar en trámite",
        "area_type": "unpopulated",
        "status": FlightPermission.STATUS_REQUESTED,
        "latitude": "-33.1",
        "longitude": "-70.1",
    }
    data.update(kwargs)
    return FlightPermission.objects.create(**data)


# ── permisos: el del mapa MÁS el de los permisos de vuelo ────────────────────


@pytest.mark.django_db
class TestPermissions:
    def test_it_is_403_without_the_flight_permit_permission(self, world):
        assert login_as(AIR).get(PENDING).status_code == 403

    def test_the_permit_permission_alone_is_not_enough_without_the_map_one(self, world):
        assert login_as(PERMITS).get(PENDING).status_code == 403

    def test_the_sites_permission_does_not_open_it(self, world):
        assert login_as(AIR, SITES).get(PENDING).status_code == 403

    def test_it_opens_with_both_permissions(self, world):
        assert login_as(AIR, PERMITS).get(PENDING).status_code == 200

    def test_the_layer_is_offered_only_with_the_flight_permit_permission(
        self, snapshot, world
    ):
        for codes, expected in (
            ((AIR,), []),
            ((AIR, SITES), ["sites"]),
            ((AIR, PERMITS), ["permits", "pending"]),
        ):
            html = login_as(*codes, member_of=world["mine"]).get(PAGE).content.decode()
            keys = [o["key"] for o in config_of(html)["ownLayers"]]
            assert keys == expected, codes

    def test_the_pending_url_travels_but_no_pending_data_does(self, snapshot, world):
        requested(world, "JEJ-2026-014", location="Sitio secreto 9")
        html = (
            login_as(AIR, PERMITS, member_of=world["mine"]).get(PAGE).content.decode()
        )
        offered = {o["key"]: o["url"] for o in config_of(html)["ownLayers"]}
        assert offered["pending"] == PENDING
        for private in ("JEJ-2026-014", "Sitio secreto 9", "-33.1"):
            assert private not in html.split('id="air-config"')[0], private


# ── qué entra ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestContent:
    def test_an_empty_list_is_empty_and_has_nothing_unplaced(self, world):
        client = login_as(AIR, PERMITS, member_of=world["mine"])
        data = payload_of(client.get(PENDING))
        assert data["layer"] == "pending"
        assert data["items"] == [] and data["unplaced"] == 0

    def test_a_point_with_a_radius_travels_with_it_and_a_point_alone_with_none(
        self, world
    ):
        requested(world, "F-circle", radius_km="2.50", latitude="-33.2")
        requested(world, "F-point", radius_km=None, latitude="-33.3")
        client = login_as(AIR, PERMITS, member_of=world["mine"])
        got = {i["folio"]: i for i in items(client.get(PENDING))}
        assert got["F-circle"]["radius_km"] == pytest.approx(2.5)
        assert got["F-point"]["radius_km"] is None
        assert got["F-circle"]["lat"] == pytest.approx(-33.2)
        assert got["F-circle"]["site"] == "CC-A"
        assert got["F-circle"]["status"] == "Requested"

    def test_without_coordinates_it_is_not_drawn_but_it_is_counted(self, world):
        requested(world, "F-none", latitude=None, longitude=None)
        requested(world, "F-half", longitude=None)
        requested(world, "F-ok")
        client = login_as(AIR, PERMITS, member_of=world["mine"])
        data = payload_of(client.get(PENDING))
        assert [i["folio"] for i in data["items"]] == ["F-ok"]
        assert data["unplaced"] == 2

    def test_the_site_of_the_cost_center_is_never_used_as_a_fallback(self, world):
        # La faena A tiene coordenadas; el permiso sin ubicación no hereda las suyas.
        requested(world, "F-none", latitude=None, longitude=None)
        client = login_as(AIR, PERMITS, member_of=world["mine"])
        data = payload_of(client.get(PENDING))
        assert data["items"] == [] and data["unplaced"] == 1

    def test_a_request_without_dates_or_dgac_number_does_not_break(self, world):
        # `_permit_entry` hace `valid_until.isoformat()`: con una fecha nula rompe (500).
        requested(world, "F-null", valid_from=None, valid_until=None)
        client = login_as(AIR, PERMITS, member_of=world["mine"])
        response = client.get(PENDING)
        assert response.status_code == 200
        (item,) = items(response)
        assert item["valid_from"] is None and item["valid_until"] is None
        assert item["number"] == ""
        assert item["folio"] == "F-null"

    def test_the_proposed_dates_and_the_registration_day_travel(self, world):
        today = timezone.localdate()
        requested(
            world,
            "F-dates",
            permission_number="N-77",
            valid_from=today + timedelta(days=3),
            valid_until=today + timedelta(days=9),
        )
        client = login_as(AIR, PERMITS, member_of=world["mine"])
        (item,) = items(client.get(PENDING))
        assert item["valid_from"] == (today + timedelta(days=3)).isoformat()
        assert item["valid_until"] == (today + timedelta(days=9)).isoformat()
        assert item["number"] == "N-77"
        assert item["created_on"] == timezone.localdate().isoformat()

    def test_only_requested_and_active_permits_enter(self, world):
        today = timezone.localdate()
        requested(world, "F-req")
        requested(world, "F-denied", status=FlightPermission.STATUS_DENIED)
        requested(world, "F-expired", status=FlightPermission.STATUS_EXPIRED)
        requested(world, "F-done", status=FlightPermission.STATUS_COMPLETED)
        requested(world, "F-off", is_active=False)
        requested(
            world,
            "F-approved",
            status=FlightPermission.STATUS_APPROVED,
            valid_from=today,
            valid_until=today + timedelta(days=4),
        )
        requested(
            world,
            "F-old",
            status=FlightPermission.STATUS_APPROVED,
            valid_from=today - timedelta(days=9),
            valid_until=today - timedelta(days=1),
        )
        client = login_as(AIR, PERMITS, member_of=world["mine"])
        data = payload_of(client.get(PENDING))
        assert [i["folio"] for i in data["items"]] == ["F-req"]
        assert data["unplaced"] == 0

    def test_a_pending_permit_never_enters_the_current_permits_layer(self, world):
        requested(world, "F-req")
        client = login_as(AIR, PERMITS, member_of=world["mine"])
        numbers = [i["number"] for i in items(client.get(LAYERS + "?layer=permits"))]
        assert numbers == ["P-a"]


# ── tenant ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTenantIsolation:
    @pytest.fixture
    def both(self, world):
        requested(world, "F-mine")
        requested(
            world,
            "F-theirs",
            cost_center=world["center_b"],
            latitude="-23.5",
        )
        requested(
            world,
            "F-theirs-none",
            cost_center=world["center_b"],
            latitude=None,
            longitude=None,
        )
        return world

    def test_one_company_never_sees_the_others_pending_permit(self, both):
        client = login_as(AIR, PERMITS, member_of=both["mine"])
        data = payload_of(client.get(PENDING))
        assert [i["folio"] for i in data["items"]] == ["F-mine"]
        assert data["unplaced"] == 0  # el sin ubicación ajeno tampoco se cuenta

    def test_the_other_company_sees_only_its_own(self, both):
        client = login_as(AIR, PERMITS, member_of=both["other"])
        data = payload_of(client.get(PENDING))
        assert [i["folio"] for i in data["items"]] == ["F-theirs"]
        assert data["unplaced"] == 1


# ── la respuesta es dato inerte y sin personas ni aeronaves ──────────────────


@pytest.mark.django_db
class TestTheResponse:
    def test_only_the_approved_keys_travel_no_operators_no_aircraft(self, world):
        requested(world, "F-keys")
        client = login_as(AIR, PERMITS, member_of=world["mine"])
        (item,) = items(client.get(PENDING))
        assert set(item) == {
            "id",
            "folio",
            "number",
            "site",
            "location",
            "status",
            "created_on",
            "valid_from",
            "valid_until",
            "lat",
            "lon",
            "radius_km",
        }

    def test_markup_is_escaped_and_the_response_is_private(self, world):
        requested(world, "F-xss", location="<script>alert(1)</script>&x")
        response = login_as(AIR, PERMITS, member_of=world["mine"]).get(PENDING)
        assert response["Content-Type"].startswith("application/json")
        assert "private" in response["Cache-Control"]
        raw = response.content.decode()
        assert "<script>" not in raw and "\\u003cscript\\u003e" in raw
        assert json.loads(raw)["items"][0]["location"] == "<script>alert(1)</script>&x"


# ── textos traducidos ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_strings_are_translated_in_the_config(snapshot, world):
    from django.utils import translation

    keys = (
        "layerPending",
        "pendingWord",
        "registeredOn",
        "proposedValidity",
        "validityUnset",
        "pendingUnplaced",
    )
    en = config_of(
        login_as(AIR, PERMITS, member_of=world["mine"]).get(PAGE).content.decode()
    )["i18n"]
    assert en["layerPending"] == "Permits in process"
    assert en["pendingWord"] == "Permit in process"
    with translation.override("es"):
        client = login_as(PERMITS, AIR, member_of=world["mine"])
        client.defaults["HTTP_ACCEPT_LANGUAGE"] = "es"
        page = client.get(PAGE).content.decode()
        es = config_of(page)["i18n"]
    assert es["layerPending"] == "Permisos en trámite"
    assert es["registeredOn"] == "registrado el {date}"
    assert es["proposedValidity"] == "vigencia propuesta {from} – {until}"
    assert es["validityUnset"] == "vigencia aún sin fijar por la DGAC"
    assert es["pendingUnplaced"] == "{n} en trámite sin ubicación: no se dibujan."
    assert all(es[key] != en[key] for key in keys)
    assert "Contorno punteado y reloj de arena" in page


@pytest.mark.django_db
def test_the_legend_note_is_in_the_page_hidden_until_the_layer_is_offered(
    snapshot, world
):
    html = login_as(AIR, PERMITS).get(PAGE).content.decode()
    assert re.search(r'id="air-legend-pending-note"[^>]*\bhidden\b', html)
    assert "Not an authorization to fly." in html


# ── el CSS ───────────────────────────────────────────────────────────────────


def _rule(selector):
    return re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS).group(1)


class TestTheStyle:
    def test_the_pane_sits_below_the_halo_of_the_zones_and_the_overlay_pane(self):
        z = int(
            _rule(".air-map .leaflet-airPending-pane").split("z-index:")[1].strip(" ;")
        )
        assert z < 399 < 400

    def test_the_line_is_dotted_without_fill_and_round(self):
        rule = _rule(".air-own-pending")
        assert "stroke-dasharray: 1 5" in rule and "stroke-linecap: round" in rule
        assert "stroke-width: 2.5px" in rule
        assert "fill: none" in rule
        assert "var(--id-air-line-pending)" in rule

    def test_the_halo_is_four_pixels_and_dark(self):
        rule = _rule(".air-own-pending-halo")
        assert "stroke-width: 4px" in rule and "var(--id-air-halo)" in rule

    def test_the_token_is_a_fixed_magenta_not_the_amber_of_restricted_zones(self):
        token = re.search(r"--id-air-line-pending:\s*(#[0-9a-fA-F]{6})", CSS).group(1)
        assert token == "#ff5ce1"
        assert token != re.search(r"--id-air-line-restricted:\s*(#\w+)", CSS).group(1)
        root = CSS.split(":root {")[1].split("\n}")[0]
        assert "--id-air-line-pending" in root

    def test_the_legend_swatch_has_a_dotted_border(self):
        assert "border-style: dotted" in _rule(".air-swatch--own-pending")


# ── el script, en Node, contra un Leaflet que registra lo que se crea ────────

NODE_SCRIPT = r"""
const fs = require('fs');
let raw = '';
process.stdin.on('data', d => raw += d);
process.stdin.on('end', async () => {
  const input = JSON.parse(raw);
  const tick = async () => { for (let i = 0; i < 8; i += 1) { await new Promise(r => setImmediate(r)); } };
  const created = [], onMap = new Set(), panes = [], fetched = [], nodes = {};
  const stub = () => ({
    textContent: '', value: '', checked: false, hidden: false, dataset: {}, style: {}, options: {},
    listeners: {}, children: [], firstChild: null, className: '', innerHTML: '',
    classList: { toggle() {}, add() {}, remove() {} },
    appendChild(c) { this.children.push(c); return c; }, insertBefore() {},
    setAttribute() {}, removeAttribute() {}, focus() {}, closest() { return null; },
    querySelector() { return null; }, querySelectorAll() { return []; },
    addEventListener(n, f) { (this.listeners[n] = this.listeners[n] || []).push(f); },
  });
  const document = {
    getElementById(id) {
      if (id === 'air-config') { return { textContent: JSON.stringify(input.cfg) }; }
      return nodes[id] = nodes[id] || stub();
    },
    createElement: stub, createElementNS: stub, querySelector() { return null; },
    addEventListener() {}, documentElement: stub(),
  };
  const make = (kind) => (a, b) => {
    const l = { kind, options: b || {}, args: a, tips: [],
      on() { return l; }, bindTooltip(node) { l.tips.push(node); return l; }, setLatLngs() {},
      setStyle() {}, eachLayer() {}, bringToFront() {} };
    l.addTo = () => { onMap.add(l); return l; };
    created.push(l);
    return l;
  };
  const map = { on() { return map; }, getSize: () => ({ x: 500, y: 400 }), fitBounds() {}, setView() {},
    addLayer() {}, removeLayer(l) { onMap.delete(l); }, createPane(name) { panes.push(name); },
    getZoom: () => 9, doubleClickZoom: { enable() {}, disable() {} } };
  const L = {
    map: () => map, canvas: () => ({ tag: 'canvas' }),
    svg: o => ({ tag: (o && o.pane) || 'overlay', _container: stub() }),
    tileLayer: make('tile'), control: { layers: make('control') },
    marker: make('marker'), circleMarker: make('circleMarker'), polyline: make('polyline'),
    circle: make('circle'), layerGroup: make('group'), divIcon: o => o, DomEvent: { stopPropagation() {} },
    geoJSON: make('geoJSON'),
  };
  const window = {
    L, AirspaceSearch: require('./static/js/airspace-search.js'), location: { search: '' },
    console: { error: () => {} }, setTimeout, clearTimeout,
  };
  class MutationObserver { observe() {} }
  const fakeFetch = async (url) => {
    fetched.push(url);
    const body = url.indexOf('layer=pending') >= 0 ? input.pending : input.data;
    return { ok: true, status: 200, json: async () => body };
  };
  const code = fs.readFileSync('./static/js/airspace-map.js', 'utf8');
  new Function('window', 'document', 'L', 'fetch', 'MutationObserver', 'getComputedStyle', 'console', code)(
    window, document, L, fakeFetch, MutationObserver, () => ({ getPropertyValue: () => '' }), window.console);
  await tick();
  const legend = nodes['air-legend-own'];
  const label = legend.children[0];
  const box = label.children[0];
  const before = { fetched: fetched.slice(), checked: box.checked, on: created.filter(l => onMap.has(l) && l.options.className && l.options.className.indexOf('pending') >= 0).length,
    noteHidden: nodes['air-legend-pending-note'].hidden };
  box.checked = true;
  box.listeners.change[0]();
  await tick();
  const pending = created.filter(l => (l.options.className || '').indexOf('air-own-pending') === 0
    || (l.options.icon && String(l.options.icon.html).indexOf('air-pending') >= 0));
  const pill = label.children.filter(c => c.className === 'air-count-pill').map(c => c.textContent);
  process.stdout.write(JSON.stringify({
    panes, before, hint: nodes['air-tool-hint'].textContent, pill,
    labelText: label.children.map(c => c.textContent),
    swatchClass: label.children[1].className,
    shapes: pending.map(l => ({
      kind: l.kind, on: onMap.has(l), cls: l.options.className || l.options.icon.className,
      renderer: l.options.renderer ? l.options.renderer.tag : null,
      interactive: l.options.interactive, radius: l.options.radius || null,
      html: l.options.icon ? l.options.icon.html : null,
      tips: l.tips.map(t => ({ text: t.textContent, hasHtml: t.innerHTML !== '' })),
    })),
  }));
});
"""


@pytest.fixture
def node_run(snapshot, world):
    if NODE is None:
        pytest.skip("Node no está instalado")
    from apps.airspace.views import tab_config

    requested(
        world,
        "JEJ-2026-014",
        radius_km="3.00",
        valid_from=None,
        valid_until=None,
        location="<img src=x onerror=alert(1)>",
    )
    requested(
        world,
        "JEJ-2026-015",
        radius_km=None,
        valid_from="2026-11-02",
        valid_until="2026-11-20",
        latitude="-33.9",
    )
    requested(world, "JEJ-2026-016", latitude=None, longitude=None)
    client = login_as(AIR, PERMITS, member_of=world["mine"])
    cfg = tab_config(None, [{"key": "pending", "url": PENDING}])
    cfg["tileProviders"] = []
    pending = json.loads(client.get(PENDING).content)
    data = json.loads(client.get(reverse("airspace-data")).content)
    result = subprocess.run(  # nosec B603 B607 - node local, argumentos fijos del propio test
        [NODE, "-e", NODE_SCRIPT],
        input=json.dumps({"cfg": cfg, "data": data, "pending": pending}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


class TestTheScript:
    SECTION = JS.split("capas propias (LV-358, E3)")[1].split("function buildLegend")[0]

    def test_the_layer_starts_off_and_nothing_is_fetched_until_it_is_switched_on(
        self, node_run
    ):
        before = node_run["before"]
        assert before["checked"] is False and before["on"] == 0
        assert not any("layer=pending" in url for url in before["fetched"])
        assert before["noteHidden"] is False  # la capa se ofrece: la nota se muestra

    def test_the_pane_is_created_below_400(self, node_run):
        assert "airPending" in node_run["panes"]

    def test_each_request_is_a_dotted_circle_when_it_has_a_radius_plus_an_hourglass(
        self, node_run
    ):
        shapes = node_run["shapes"]
        circles = [s for s in shapes if s["kind"] == "circle"]
        assert sorted(s["cls"] for s in circles) == [
            "air-own-pending",
            "air-own-pending-halo",
        ]
        assert all(s["renderer"] == "airPending" for s in circles)
        assert {s["radius"] for s in circles} == {3000}
        markers = [s for s in shapes if s["kind"] == "marker"]
        assert len(markers) == 2 and all("⧗" in s["html"] for s in markers)
        assert all(s["on"] for s in shapes)

    def test_the_halo_is_not_interactive_so_the_tooltip_is_the_line_s(self, node_run):
        halo = [s for s in node_run["shapes"] if s["cls"] == "air-own-pending-halo"]
        assert halo and halo[0]["interactive"] is False and halo[0]["tips"] == []

    def test_the_tooltip_says_what_it_is_without_html(self, node_run):
        texts = {
            tip["text"]
            for s in node_run["shapes"]
            if s["kind"] == "marker"
            for tip in s["tips"]
        }
        assert (
            "Permit in process JEJ-2026-014 · CC-A · Requested · registered on "
            + timezone.localdate().strftime("%d-%m-%Y")
            + " · validity not yet set by the DGAC"
        ) in texts
        assert (
            "Permit in process JEJ-2026-015 · CC-A · Requested · registered on "
            + timezone.localdate().strftime("%d-%m-%Y")
            + " · proposed validity 02-11-2026 – 20-11-2026"
        ) in texts
        assert all(not tip["hasHtml"] for s in node_run["shapes"] for tip in s["tips"])

    def test_the_markup_of_the_data_never_becomes_html(self, node_run):
        # El rótulo no lleva `location`; el nombre del lugar no entra al DOM por innerHTML.
        assert ".innerHTML" not in self.SECTION
        tooltips = re.findall(r"bindTooltip\(([^,)]+)", self.SECTION)
        assert tooltips and all(arg.startswith("tipNode(") for arg in tooltips)
        assert "onerror" not in json.dumps(node_run["shapes"])

    def test_the_count_pill_and_the_hint_about_the_unplaced_ones(self, node_run):
        assert node_run["pill"] == ["2"]
        assert node_run["hint"].endswith("1 in process without a location: not drawn.")
        assert node_run["labelText"][2] == "Permits in process"
        assert "air-swatch--own-pending" in node_run["swatchClass"]
