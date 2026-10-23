"""LV-368 fase 4: el mini-mapa de un plan y la vista previa «lo que trae el plan».

Cuatro cosas se fijan acá:

1. la vista previa pide `geo.view_geoplan` (403) y no cruza de empresa ni de faena
   (404 a otra empresa; aviso, no datos, a otra faena de la misma);
2. con las formas reales de datos (círculo, corredor, triangular, cuadricular y un
   plan de varias áreas) el fragmento dice lo que corresponde y **no elige** por la
   persona cuando hay más de un área;
3. los datos del mapa viajan por `json_script`: un nombre de archivo malicioso no
   rompe la página;
4. el script real (`mini-map.js`), en Node, contra un Leaflet de mentira que lanza
   como el real, no cuelga con el contenedor oculto y nombra cada fallo en la consola.

Datos ficticios.
"""

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import translation

from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.geo.test_lv278_modalities import (
    LAT,
    LON,
    SQUARE_CCW,
    TRIANGLE_CCW,
    _at,
    _circle,
    _document,
    _line,
    _point,
    _polygon,
)
from apps.registry.models import Aerodrome, CostCenter

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
PREVIEW = reverse("permission-plan-preview")
READ = ("view_geoplan",)

BCN_TEXT = "come from the BCN administrative boundaries"


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


@pytest.fixture
def tenants(db):
    return (
        OperationalTenant.objects.create(name="Alfa", slug="alfa"),
        OperationalTenant.objects.create(name="Beta", slug="beta"),
    )


@pytest.fixture
def centers(tenants):
    alfa, beta = tenants
    return {
        "a": CostCenter.objects.create(code="CC-A", name="Faena A", tenant=alfa),
        "a2": CostCenter.objects.create(code="CC-A2", name="Faena A2", tenant=alfa),
        "b": CostCenter.objects.create(code="CC-B", name="Faena B", tenant=beta),
    }


@pytest.fixture
def author(db):
    return User.objects.create_user("autor-368-prev", password="pw")  # nosec B106


def make_plan(center, author, document, *, title="Plan ficticio"):
    plan = GeoPlan.objects.create(title=title, cost_center=center, created_by=author)
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


def two_circles_document(second_name="Dos"):
    """Dos áreas de verdad: el segundo círculo, a 3 km del primero."""
    ring = [
        _at(
            3000 + 120 * math.cos(2 * math.pi * i / 36),
            120 * math.sin(2 * math.pi * i / 36),
        )
        for i in range(36)
    ]
    return _document(
        _circle("Uno", 120),
        _point("Uno", 0, 0),
        _polygon(second_name, ring),
        _point(second_name, 3000, 0),
    )


def circle_document(name="Faena norte", radius_m=150):
    return _document(_circle(name, radius_m), _point(name, 0, 0))


def payload_of(html, plan):
    """El objeto que el navegador leerá: el `json_script` del fragmento."""
    match = re.search(
        rf'<script id="mini-map-{plan.pk}" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    assert match, "el fragmento no trae el json_script del mapa"
    return json.loads(match.group(1))


def get_preview(client, **params):
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "en"
    return client.get(PREVIEW, params)


# ── permisos y tenant ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestThePreviewIsGuarded:
    def test_without_view_geoplan_it_is_403(self, centers, author):
        plan = make_plan(centers["a"], author, circle_document())
        client = login_as("view_flightpermission")

        assert get_preview(client, plan=plan.pk).status_code == 403

    def test_a_plan_of_another_tenant_is_404_not_empty(self, centers, tenants, author):
        other = make_plan(centers["b"], author, circle_document())
        client = login_as(*READ, member_of=tenants[0])

        response = get_preview(client, plan=other.pk, cost_center=centers["a"].pk)

        assert response.status_code == 404

    def test_a_cost_center_of_another_tenant_is_404(self, centers, tenants, author):
        plan = make_plan(centers["a"], author, circle_document())
        client = login_as(*READ, member_of=tenants[0])

        assert (
            get_preview(client, plan=plan.pk, cost_center=centers["b"].pk).status_code
            == 404
        )

    def test_a_plan_of_another_cost_center_of_the_same_tenant_warns(
        self, centers, tenants, author
    ):
        plan = make_plan(centers["a2"], author, circle_document())
        client = login_as(*READ, member_of=tenants[0])

        response = get_preview(client, plan=plan.pk, cost_center=centers["a"].pk)

        html = response.content.decode()
        assert response.status_code == 200
        assert "CC-A2" in html and "belongs to cost center" in html
        # Un aviso no es una lectura: ni tabla ni mapa de un plan que no corresponde.
        assert "mini-map-canvas" not in html and "plan-preview-table" not in html

    @pytest.mark.parametrize(
        "raw", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"]
    )
    def test_a_malformed_or_unknown_plan_is_404_not_500(self, centers, tenants, raw):
        client = login_as(*READ, member_of=tenants[0])

        assert get_preview(client, plan=raw).status_code == 404

    def test_an_archived_plan_is_404(self, centers, tenants, author):
        plan = make_plan(centers["a"], author, circle_document())
        GeoPlan.objects.filter(pk=plan.pk).update(is_active=False)
        client = login_as(*READ, member_of=tenants[0])

        assert get_preview(client, plan=plan.pk).status_code == 404

    def test_without_a_plan_it_says_what_to_do_and_draws_nothing(
        self, centers, tenants
    ):
        client = login_as(*READ, member_of=tenants[0])

        html = get_preview(client, cost_center=centers["a"].pk).content.decode()

        assert "Choose a plan to see what it brings" in html
        assert "mini-map-canvas" not in html


# ── las formas reales de los datos ──────────────────────────────────────────


@pytest.mark.django_db
class TestWhatThePlanBrings:
    def _html(self, plan, tenants, *perms):
        client = login_as(*(perms or READ), member_of=tenants[0])
        response = get_preview(client, plan=plan.pk, cost_center=plan.cost_center_id)
        assert response.status_code == 200
        return response.content.decode()

    def test_a_circle_shows_its_centre_radius_aerodrome_and_derived_region(
        self, centers, tenants, author
    ):
        Aerodrome.objects.create(
            code="SCFA", name="Ad. Ficticio", latitude=LAT + 0.2, longitude=LON
        )
        plan = make_plan(centers["a"], author, circle_document(radius_m=150))

        html = self._html(plan, tenants)
        data = payload_of(html, plan)

        assert "What the plan brings" in html and plan.folio in html
        assert "Centre point" in html and "Radius (m)" in html
        assert "Nearest aerodrome (AMC)" in html and "SCFA" in html
        assert "What the KMZ brings" in html and "Still to fill in" in html
        # La región y la comuna salen del polígono administrativo: chip «Derivada»,
        # sin el texto largo de la BCN (la ficha es donde se confirma).
        assert "Calama" in html and "Derived from the coordinates" in html
        assert BCN_TEXT not in html
        (area,) = data["areas"]
        assert area["modality"] == "center_point"
        assert area["radius_m"] == pytest.approx(150, abs=3)
        assert area["amc"]["code"] == "SCFA" and area["amc"]["distance_km"] > 0
        assert {g["type"] for g in area["geometries"]} == {"Point", "Polygon"}
        # La centro del mapa es la que la tabla declara: (lat, lon), el orden de Leaflet.
        assert area["center"] == [
            pytest.approx(LAT, abs=1e-4),
            pytest.approx(LON, abs=1e-4),
        ]

    def test_the_tiles_are_the_configured_ones_and_nothing_else(
        self, centers, tenants, author, settings
    ):
        plan = make_plan(centers["a"], author, circle_document())

        data = payload_of(self._html(plan, tenants), plan)

        assert [t["id"] for t in data["tiles"]] == [
            p["id"] for p in settings.GEO_TILE_PROVIDERS
        ]
        configured = {p["url"] for p in settings.GEO_TILE_PROVIDERS}
        assert {t["url"] for t in data["tiles"]} <= configured

    def test_a_corridor_draws_its_axis_and_has_no_radius(
        self, centers, tenants, author
    ):
        axis = [_at(0, 0), _at(0, 300), _at(300, 300)]
        plan = make_plan(centers["a"], author, _document(_line("Eje", axis)))

        html = self._html(plan, tenants)
        (area,) = payload_of(html, plan)["areas"]

        assert area["modality"] == "corridor" and area["radius_m"] is None
        # El eje y el centro calculado (SIGO pide un punto central aunque no se dibujara).
        assert {g["type"] for g in area["geometries"]} == {"LineString", "Point"}
        assert "Start and end points" in html

    @pytest.mark.parametrize(
        ("ring", "modality", "vertices_label"),
        [
            (TRIANGLE_CCW, "triangle", "Area vertices"),
            (SQUARE_CCW, "quadrilateral", "Area vertices"),
        ],
    )
    def test_a_triangle_and_a_quadrilateral_draw_their_vertices(
        self, centers, tenants, author, ring, modality, vertices_label
    ):
        plan = make_plan(centers["a"], author, _document(_polygon("Area", ring)))

        html = self._html(plan, tenants)
        (area,) = payload_of(html, plan)["areas"]

        assert area["modality"] == modality and area["radius_m"] is None
        polygon = next(g for g in area["geometries"] if g["type"] == "Polygon")
        # El anillo viaja cerrado: los vértices más el de cierre.
        assert len(polygon["coordinates"][0]) == len(ring) + 1
        assert vertices_label in html and "Centre point (calculated)" in html

    def test_an_irregular_area_draws_the_enclosing_circle_dashed(
        self, centers, tenants, author
    ):
        pentagon = [_at(0, 0), _at(200, 0), _at(260, 160), _at(100, 260), _at(-60, 160)]
        plan = make_plan(centers["a"], author, _document(_polygon("Penta", pentagon)))

        (area,) = payload_of(self._html(plan, tenants), plan)["areas"]

        assert area["enclosing"] is True and area["radius_m"] > 0

    def test_several_areas_are_not_chosen_between_and_point_to_the_split(
        self, centers, tenants, author
    ):
        plan = make_plan(centers["a"], author, two_circles_document())

        html = self._html(plan, tenants, *READ, "add_flightrequest")
        data = payload_of(html, plan)

        assert "2 areas: separate them into flight requests." in html
        assert reverse("geo-plan-split", args=[plan.pk]) in html
        # Ningún centro que declarar: no hay tabla de un área, y el mapa dibuja las dos.
        assert "plan-preview-table" not in html
        assert len(data["areas"]) == 2

    def test_the_split_link_needs_add_flightrequest(self, centers, tenants, author):
        plan = make_plan(centers["a"], author, two_circles_document())

        html = self._html(plan, tenants)

        assert "areas: separate them into flight requests." in html
        assert reverse("geo-plan-split", args=[plan.pk]) not in html

    def test_a_plan_without_content_says_so(self, centers, tenants, author):
        plan = GeoPlan.objects.create(
            title="Vacío", cost_center=centers["a"], created_by=author
        )

        html = self._html(plan, tenants)

        assert "no area that can be read" in html
        assert "mini-map-canvas" not in html


@pytest.mark.django_db
def test_the_preview_speaks_spanish_to_a_spanish_session(centers, tenants, author):
    """Las cadenas nuevas están traducidas (un literal con `%(n)s` no lo hace `{% translate %}`)."""
    plan = make_plan(centers["a"], author, two_circles_document())
    client = login_as(*READ, member_of=tenants[0])
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "es"

    html = client.get(
        PREVIEW, {"plan": plan.pk, "cost_center": centers["a"].pk}
    ).content.decode()

    assert "2 áreas: separar en solicitudes de vuelo." in html
    assert "Mapa" in html and "Lo que trae el plan" in html
    # Y el estado vacío, y el aviso de otra faena.
    empty = client.get(PREVIEW).content.decode()
    assert "Elija un plan para ver lo que trae" in empty


@pytest.mark.django_db
def test_the_map_data_travels_by_json_script_never_raw(centers, tenants, author):
    """Un nombre con `</script>` no rompe la página ni se interpola como HTML."""
    hostile = "</script><img src=x onerror=alert(1)>"
    plan = make_plan(centers["a"], author, two_circles_document(hostile), title=hostile)
    client = login_as(*READ, member_of=tenants[0])

    html = get_preview(
        client, plan=plan.pk, cost_center=centers["a"].pk
    ).content.decode()

    assert "<img src=x" not in html
    assert hostile not in html
    assert f'id="mini-map-{plan.pk}" type="application/json"' in html


# ── el script, en Node, contra un Leaflet que lanza como el real ────────────

NODE_SCRIPT = r"""
const fs = require('fs');
let raw = '';
process.stdin.on('data', d => raw += d);
process.stdin.on('end', () => {
  const input = JSON.parse(raw);
  const source = fs.readFileSync('./static/js/geo/mini-map.js', 'utf8');

  function makeEnv(options) {
    const opts = Object.assign({ size: [400, 256], hasDetails: true, desktop: true, leaflet: true,
      config: input.good, mapThrows: false }, options || {});
    const errors = [], calls = { geoJSON: [], circleMarker: 0, circle: 0, polyline: 0, tooltips: [],
      fitBounds: 0, setView: 0, maps: 0, tiles: [] };
    const listeners = {};
    const note = { hidden: true };
    const container = {
      dataset: { miniMapConfig: 'cfg' }, hidden: false,
      clientWidth: opts.size[0], clientHeight: opts.size[1], parentNode: { querySelector: () => note },
      closest: () => (opts.hasDetails ? details : null),
    };
    const details = {
      open: false, listeners: {},
      addEventListener(n, f) { (this.listeners[n] = this.listeners[n] || []).push(f); },
      removeEventListener(n, f) { this.listeners[n] = (this.listeners[n] || []).filter(x => x !== f); },
      querySelector: () => note,
    };
    const bodyListeners = {};
    const document = {
      readyState: 'complete',
      getElementById: id => (opts.config === null ? null : { textContent: JSON.stringify(opts.config) }),
      querySelectorAll: () => [container],
      addEventListener() {},
      body: { addEventListener(n, f) { (bodyListeners[n] = bodyListeners[n] || []).push(f); } },
    };
    const layer = () => { const l = { addTo() { return l; }, bindTooltip(t) { calls.tooltips.push(t); return l; } }; return l; };
    const check = g => {
      if (!g || typeof g !== 'object') { throw new TypeError('Invalid GeoJSON object.'); }
      if (JSON.stringify(g.coordinates).includes('boom')) { throw new Error('boom'); }
      if (!Array.isArray(g.coordinates) || !g.coordinates.length) {
        throw new TypeError("Cannot read properties of undefined (reading 'length')");
      }
    };
    const L = {
      Browser: { mobile: false },
      map() {
        if (opts.mapThrows) { throw new Error('Map container is already initialized.'); }
        calls.maps += 1;
        const map = {
          getSize: () => ({ x: container.clientWidth, y: container.clientHeight }),
          // Como Leaflet: mover la vista de un mapa sin tamaño produce NaN y lanza.
          fitBounds() { if (!container.clientWidth) { throw new Error('Invalid LatLng object: (NaN, NaN)'); } calls.fitBounds += 1; },
          setView() { if (!container.clientWidth) { throw new Error('Invalid LatLng object: (NaN, NaN)'); } calls.setView += 1; },
        };
        return map;
      },
      tileLayer(url) { calls.tiles.push(url); return layer(); },
      layerGroup: layer,
      circleMarker() { calls.circleMarker += 1; return layer(); },
      circle() { calls.circle += 1; return layer(); },
      polyline() { calls.polyline += 1; return layer(); },
      geoJSON(geometry) { check(geometry); calls.geoJSON.push(geometry.type); return layer(); },
    };
    const window = {
      L: opts.leaflet ? L : undefined, setTimeout: fn => { fn(); return 0; },
      console: { error: (...a) => errors.push(a.join(' ')) },
      matchMedia: () => ({ matches: opts.desktop }),
    };
    new Function('window', 'document', source)(window, document);
    return { errors, calls, container, details, note, window, bodyListeners, document };
  }

  const area = (extra) => Object.assign({ name: 'A', modality: 'center_point', center: [-22.3, -68.9],
    radius_m: 150, enclosing: false, amc: null,
    geometries: [{ type: 'Point', coordinates: [-68.9, -22.3] },
                 { type: 'Polygon', coordinates: [[[-68.9, -22.3], [-68.89, -22.3], [-68.89, -22.29], [-68.9, -22.3]]] }] }, extra || {});
  const cfg = areas => ({ tiles: [{ url: 'https://tiles.test/{z}/{x}/{y}.png', attribution: 'x', default: true }],
    areas, i18n: { km: 'km' } });
  const out = {};

  // 1. visible, desktop: dibuja, mueve la vista, abre el <details>, sin errores.
  let env = makeEnv({ config: cfg([area({ amc: { code: 'SCFA', name: 'Ad', lat: -22.1, lon: -68.9, distance_km: 22 } })]) });
  out.circle = { errors: env.errors, calls: env.calls, state: env.container.dataset.miniMapState, open: env.details.open,
    fallback: env.note.hidden };

  // 2. la modalidad sin radio y la circunferencia que encierra (discontinua).
  env = makeEnv({ config: cfg([area({ modality: 'triangle', radius_m: null, geometries: [{ type: 'Polygon', coordinates: [[[1, 1], [2, 1], [2, 2], [1, 1]]] }] })]) });
  out.triangle = { errors: env.errors, circle: env.calls.circle, geo: env.calls.geoJSON };
  env = makeEnv({ config: cfg([area({ modality: 'quadrilateral', enclosing: true, geometries: [{ type: 'Polygon', coordinates: [[[1, 1], [2, 1], [2, 2], [1, 1]]] }] })]) });
  out.enclosing = { errors: env.errors, circle: env.calls.circle };
  env = makeEnv({ config: cfg([area({ modality: 'corridor', radius_m: null, geometries: [{ type: 'LineString', coordinates: [[1, 1], [2, 2]] }] })]) });
  out.corridor = { errors: env.errors, geo: env.calls.geoJSON, circle: env.calls.circle };

  // 3. una geometría mala se nombra y no tumba el resto.
  env = makeEnv({ config: cfg([area({ modality: 'triangle', geometries: [{ type: 'Polygon', coordinates: [[['boom']]] }] })]) });
  out.bad = { errors: env.errors, state: env.container.dataset.miniMapState, fallback: env.note.hidden, markers: env.calls.circleMarker };

  // 4. contenedor oculto (details cerrado en móvil): nada se mueve hasta abrir.
  env = makeEnv({ size: [0, 0], desktop: false, config: cfg([area()]) });
  out.hiddenBefore = { errors: env.errors, maps: env.calls.maps, moves: env.calls.fitBounds + env.calls.setView, open: env.details.open };
  env.container.clientWidth = 400; env.container.clientHeight = 256; env.details.open = true;
  (env.details.listeners.toggle || []).slice().forEach(f => f());
  out.hiddenAfter = { errors: env.errors, maps: env.calls.maps, fit: env.calls.fitBounds, state: env.container.dataset.miniMapState };

  // 4a. Chromium conserva las medidas del contenido de un <details> CERRADO: con tamaño y cerrado
  // tampoco se dibuja; se dibuja al abrirlo.
  env = makeEnv({ size: [400, 256], desktop: false, config: cfg([area()]) });
  out.closedButMeasurable = { maps: env.calls.maps, open: env.details.open };
  env.details.open = true;
  (env.details.listeners.toggle || []).slice().forEach(f => f());
  out.closedButMeasurableOpened = { maps: env.calls.maps, errors: env.errors };

  // 4b. escritorio con el contenedor aún sin tamaño: abre, espera y dibuja cuando mide.
  env = makeEnv({ size: [0, 0], desktop: true, config: cfg([area()]) });
  out.desktopOpened = { open: env.details.open, maps: env.calls.maps, errors: env.errors };

  // 5. sin <details> y oculto: se dice y no se dibuja.
  env = makeEnv({ size: [0, 0], hasDetails: false, config: cfg([area()]) });
  out.noDetails = { errors: env.errors, maps: env.calls.maps };

  // 6. fallos con causa: sin Leaflet, sin datos, forma inesperada, Leaflet que lanza.
  env = makeEnv({ leaflet: false });
  out.noLeaflet = { errors: env.errors, fallback: env.note.hidden, hidden: env.container.hidden };
  env = makeEnv({ config: null });
  out.noData = { errors: env.errors, fallback: env.note.hidden };
  env = makeEnv({ config: { areas: 'nope' } });
  out.shape = { errors: env.errors };
  env = makeEnv({ mapThrows: true, config: cfg([area()]) });
  out.mapThrows = { errors: env.errors, fallback: env.note.hidden };

  // 7. iniciar dos veces no dibuja dos veces (el fragmento de htmx llega más de una vez).
  env = makeEnv({ config: cfg([area()]) });
  env.window.MiniMap.init(env.document);
  out.twice = { maps: env.calls.maps };

  process.stdout.write(JSON.stringify(out));
});
"""


@pytest.fixture(scope="module")
def node_run():
    if NODE is None:
        pytest.skip("Node no está instalado")
    result = subprocess.run(  # nosec B603 B607 - node local, argumentos fijos del propio test
        [NODE, "-e", NODE_SCRIPT],
        input=json.dumps({"good": {}}),
        capture_output=True,
        encoding="utf-8",
        cwd=ROOT,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


def test_the_map_draws_a_circle_with_its_aerodrome_and_opens_on_desktop(node_run):
    run = node_run["circle"]
    assert run["errors"] == []
    assert run["state"] == "ready" and run["open"] is True and run["fallback"] is True
    assert run["calls"]["tiles"] == ["https://tiles.test/{z}/{x}/{y}.png"]
    assert run["calls"]["fitBounds"] == 1
    # El polígono lleva halo y trazo (dos), el centro y el aeródromo son marcadores y hay una
    # línea punteada hacia el aeródromo; el aeródromo trae su rótulo con la distancia.
    assert run["calls"]["geoJSON"] == ["Polygon", "Polygon"]
    assert run["calls"]["circleMarker"] == 2 and run["calls"]["polyline"] == 1
    assert run["calls"]["tooltips"] == ["SCFA · Ad · 22 km"]


def test_each_modality_draws_what_it_has_and_only_that(node_run):
    assert node_run["triangle"]["errors"] == [] and node_run["triangle"]["circle"] == 0
    assert node_run["corridor"]["geo"] == ["LineString", "LineString"]
    assert node_run["corridor"]["circle"] == 0
    # El círculo que encierra un área irregular sí: es lo que se declara.
    assert node_run["enclosing"]["circle"] == 1


def test_one_bad_geometry_is_named_and_does_not_take_the_map_down(node_run):
    bad = node_run["bad"]
    assert bad["errors"] == ["mini-map: draw triangle: boom"]
    assert bad["state"] == "ready" and bad["fallback"] is True
    assert bad["markers"] >= 1


def test_a_hidden_container_is_not_moved_until_it_has_a_size(node_run):
    before, after = node_run["hiddenBefore"], node_run["hiddenAfter"]
    # En móvil el <details> queda cerrado y el mapa ni se crea (Leaflet con tamaño 0 puede colgar).
    assert before == {"errors": [], "maps": 0, "moves": 0, "open": False}
    assert after["errors"] == [] and after["maps"] == 1 and after["fit"] == 1
    assert after["state"] == "ready"
    # Medible pero cerrado (así lo reporta Chromium): tampoco se dibuja hasta abrirlo.
    assert node_run["closedButMeasurable"] == {"maps": 0, "open": False}
    assert node_run["closedButMeasurableOpened"] == {"maps": 1, "errors": []}
    # En escritorio se abre solo, pero sigue sin dibujar mientras mida 0.
    assert node_run["desktopOpened"] == {"open": True, "maps": 0, "errors": []}
    # Sin <details> al que esperar, se dice que no se dibujó en vez de fallar callado.
    assert node_run["noDetails"] == {
        "errors": ["mini-map: container: hidden, not drawn"],
        "maps": 0,
    }


def test_every_failure_names_its_cause_and_shows_the_fallback(node_run):
    assert node_run["noLeaflet"] == {
        "errors": ["mini-map: leaflet: Leaflet is not loaded"],
        "fallback": False,
        "hidden": True,
    }
    assert node_run["noData"]["errors"] == ["mini-map: data: no data element"]
    assert node_run["noData"]["fallback"] is False
    assert node_run["shape"]["errors"] == ["mini-map: data: unexpected data shape"]
    assert node_run["mapThrows"]["errors"] == [
        "mini-map: map: Map container is already initialized."
    ]
    assert node_run["mapThrows"]["fallback"] is False


def test_starting_twice_does_not_draw_twice(node_run):
    assert node_run["twice"]["maps"] == 1
