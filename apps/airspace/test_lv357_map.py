"""LV-357 (fase 3): la pestaña «Espacio aéreo» de Entorno y sus dos endpoints de datos.

Sin red y sin datos reales: la foto sale del KML sintético del repositorio (`import_airspace_zones`).
Se fija: 403 sin `view_airspacefeature` (LV-268) en las tres rutas, 404 con guía de importación sin foto,
el JSON (ETag y 304, sólo activas, sin ayudas de dibujo, sin HTML sin escapar, límites verticales
COMO los escribió la fuente), `near/` con las mismas funciones de geometría que el servidor, el buscador
del cliente contra el de Python (paridad por Node) y que la pantalla no diga lo que no debe.
"""

import json
import re
import shutil
import socket
import subprocess
import urllib.request
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone, translation

from apps.airspace import payload
from apps.airspace.models import AirspaceFeature, AirspaceSnapshot
from apps.core.testing import login_as as _login_as
from apps.environment import tabs
from apps.geo import airspace_search

ROOT = Path(__file__).resolve().parents[2]
KML = Path(__file__).parent / "test_data" / "synthetic_airspace.kml"
VIEW = "view_airspacefeature"
PAGE, DATA, NEAR = (
    reverse("airspace-map"),
    reverse("airspace-data"),
    reverse("airspace-near"),
)
INSIDE_D66 = {"lat": -33.19, "lon": -70.42}  # dentro del triángulo SC-D66


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


@pytest.fixture(autouse=True)
def quiet(settings, monkeypatch):
    """Sin tiempo ni centelleo que consulten nada, y a la red se le prohíbe salir."""
    settings.WEATHER_ENABLED = False
    settings.WEATHER_DEFAULT_LABEL = ""

    def refuse(*args, **kwargs):
        raise AssertionError("la pestaña Espacio aéreo no puede salir a la red")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def login_as(*codenames, lang="en"):
    """El cliente de `apps.core.testing`, pidiendo el idioma (la fuente está en inglés)."""
    client = _login_as(*codenames)
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = lang
    return client


@pytest.fixture
def snapshot(db):
    call_command("import_airspace_zones", "--file", str(KML), verbosity=0)
    return AirspaceSnapshot.objects.get(is_current=True)


def body(response):
    return json.loads(response.content)


# ── permisos (LV-268) ───────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("url", [PAGE, DATA, NEAR + "?lat=-33&lon=-70"])
def test_each_route_is_403_without_the_model_permission(snapshot, url):
    assert login_as().get(url).status_code == 403
    # Otro permiso del mismo dominio no sirve: se pide EXACTAMENTE `view_airspacefeature`.
    assert login_as("view_userweatherlocation").get(url).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", [PAGE, DATA, NEAR + "?lat=-33&lon=-70"])
def test_anonymous_goes_to_the_login(snapshot, client, url):
    response = client.get(url)
    assert response.status_code == 302
    assert "login" in response["Location"]


@pytest.mark.django_db
def test_the_tab_appears_for_who_can_view_it_and_only_then(snapshot):
    viewer = login_as(VIEW)
    assert [t["key"] for t in tabs.tabs_for(viewer.user)] == ["airspace"]
    page = viewer.get(PAGE).content.decode()
    assert f'href="{PAGE}"' in page and "aria-current" in page
    assert (
        tabs.tabs_for(login_as("view_userweatherlocation").user)[0]["key"] != "airspace"
    )


@pytest.mark.django_db
def test_the_hub_sends_a_viewer_only_user_to_the_airspace_tab(snapshot):
    response = login_as(VIEW).get(reverse("environment-hub"))
    assert response.status_code == 302 and response["Location"] == PAGE


# ── la pantalla ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_without_a_snapshot_the_page_is_404_with_an_import_guide():
    response = login_as(VIEW).get(PAGE)
    html = response.content.decode()
    assert response.status_code == 404
    assert "import_airspace_zones --file" in html and "--dry-run" in html
    assert 'id="air-map"' not in html  # sin foto no se dibuja un mapa vacío


@pytest.mark.django_db
def test_without_a_snapshot_the_data_is_404_json():
    response = login_as(VIEW).get(DATA)
    assert response.status_code == 404 and body(response) == {"error": "no_snapshot"}


@pytest.mark.django_db
def test_the_page_shows_counts_source_attribution_and_the_official_reference(snapshot):
    html = login_as(VIEW).get(PAGE).content.decode()
    assert "Sensitive-zones map delivered by the DGAC (Google My Maps)" in html
    assert payload.AIP_ENR_URL in html
    assert 'id="air-config"' in html and 'id="air-map"' in html
    for kind, count in (("Aerodrome", 2), ("Airport", 1)):
        # LV-367: the label carries its icon inside the <dt>; the figure stays in its own <dd>.
        assert re.search(rf"<dt>(?:<svg.*?</svg>)?{kind}</dt><dd>{count}</dd>", html)
    # Una sola advertencia «Referencial» (la de la cabecera común) y ningún veredicto.
    assert html.count('class="env-referential"') == 1
    lowered = html.lower()
    for forbidden in ("can fly", "cannot fly", "cleared to", "go/no-go", "active now"):
        assert forbidden not in lowered


@pytest.mark.django_db
def test_a_photo_older_than_30_days_is_flagged_amber_and_a_fresh_one_is_not(snapshot):
    client = login_as(VIEW)
    assert "air-photo--stale" not in client.get(PAGE).content.decode()
    AirspaceSnapshot.objects.filter(pk=snapshot.pk).update(
        fetched_at=timezone.now() - timedelta(days=45)
    )
    html = client.get(PAGE).content.decode()
    assert "air-photo--stale" in html and "The copy is 45 days old" in html
    assert "▲" in html  # nunca sólo color


@pytest.mark.django_db
def test_the_page_is_translated_to_spanish(snapshot):
    html = login_as(VIEW, lang="es").get(PAGE).content.decode()
    assert "Espacio aéreo y aeródromos" in html
    assert "Mapa de zonas sensibles entregado por la DGAC (Google My Maps)" in html
    assert "Referencia oficial: AIP-Chile, ENR 5.1" in html


@pytest.mark.django_db
def test_the_embedded_config_is_json_script_and_carries_no_zone_text(snapshot):
    html = login_as(VIEW).get(PAGE).content.decode()
    assert '<script id="air-config" type="application/json">' in html
    assert "Prueba Uno" not in html  # los datos de la fuente sólo van por `data.json`


# ── data.json ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_json_carries_the_snapshot_sha_as_etag_and_answers_304(snapshot):
    client = login_as(VIEW)
    first = client.get(DATA)
    assert first.status_code == 200
    assert first["ETag"] == f'"{snapshot.sha256}"'
    assert first["Cache-Control"] == "private, no-cache"
    again = client.get(DATA, HTTP_IF_NONE_MATCH=first["ETag"])
    assert again.status_code == 304 and again.content == b""
    assert again["ETag"] == first["ETag"]
    weak = client.get(DATA, HTTP_IF_NONE_MATCH='W/"other", ' + first["ETag"])
    assert weak.status_code == 304
    assert client.get(DATA, HTTP_IF_NONE_MATCH='"stale"').status_code == 200


@pytest.mark.django_db
def test_the_json_serves_only_active_features_and_no_drawing_aids(snapshot):
    client = login_as(VIEW)
    names = {f["name"] for f in body(client.get(DATA))["features"]}
    kinds = {f["kind"] for f in body(client.get(DATA))["features"]}
    assert "aux" not in kinds
    assert not any("Medida" in n or "Punto centrado" in n for n in names)
    victim = AirspaceFeature.objects.filter(kind="prohibited").first()
    AirspaceFeature.objects.filter(pk=victim.pk).update(is_active=False)
    ids = {f["id"] for f in body(client.get(DATA))["features"]}
    assert str(victim.pk) not in ids


@pytest.mark.django_db
def test_the_json_keeps_the_sources_limits_as_text_and_never_as_numbers(snapshot):
    features = {
        f["code"]: f for f in body(login_as(VIEW).get(DATA))["features"] if f["code"]
    }
    r54 = features["SC-R54"]
    assert isinstance(r54["vertical"], str) and isinstance(r54["schedule"], str)
    assert "9000 FT AMSL" in r54["vertical"] and "H24" in r54["schedule"]
    p30 = features["SC-P30"]
    stored = AirspaceFeature.objects.get(code="SC-P30", is_active=True)
    # Exactamente lo que guardó el importador, con el rótulo de la fuente incluido.
    assert (
        p30["vertical"] == stored.vertical_limits_text
        and "1000 FT AGL" in p30["vertical"]
    )
    assert p30["schedule"] == stored.schedule_text and "Permanente" in p30["schedule"]
    assert "Coordinación con Torre Ficticia" in r54["text"]
    assert not any(k.endswith("_ft") or k.endswith("_m") for k in r54)


@pytest.mark.django_db
def test_points_travel_without_geometry_and_zones_with_rounded_geometry(snapshot):
    features = body(login_as(VIEW).get(DATA))["features"]
    point = next(f for f in features if f["code"] == "SCXA")
    assert "geometry" not in point and point["lat"] == -33.5
    zone = next(f for f in features if f["code"] == "SC-D66")
    assert zone["geometry"]["type"] == "Polygon" and len(zone["bbox"]) == 4
    assert all(
        len(str(c).split(".")[-1]) <= 5 for c in zone["geometry"]["coordinates"][0][0]
    )
    assert zone["dms"].endswith("W") and "°" in zone["dms"]


@pytest.mark.django_db
def test_an_aerodrome_with_an_oaci_code_links_to_the_ifis_and_others_do_not(snapshot):
    features = body(login_as(VIEW).get(DATA))["features"]
    by_code = {f["code"]: f for f in features if f["code"]}
    assert by_code["SCXA"]["ifis"].endswith("?designador=SCXA&metodo=designador")
    assert by_code["SCXA"]["ifis"].startswith("https://aipchile.dgac.gob.cl/notam")
    assert "ifis" not in by_code["SC-D66"]
    no_code = next(f for f in features if f["name"].startswith("Ad. Sin"))
    assert "ifis" not in no_code


@pytest.mark.django_db
def test_markup_in_a_name_never_reaches_the_response_as_markup(snapshot):
    AirspaceFeature.objects.filter(code="SCXA").update(
        name='<img src=x onerror=alert(1)> & "q"'
    )
    response = login_as(VIEW).get(DATA)
    raw = response.content.decode()
    assert "<img" not in raw and "<" not in raw and ">" not in raw
    assert response["Content-Type"].startswith("application/json")
    # Y el dato original llega intacto al parsear: se escapa sin perder nada.
    names = [f["name"] for f in json.loads(raw)["features"]]
    assert '<img src=x onerror=alert(1)> & "q"' in names


@pytest.mark.django_db
def test_fir_is_read_from_the_name_best_effort(snapshot):
    assert payload.fir_of("SC - R54 FIR SINTETICO\nSector Prueba") == "SINTETICO"
    assert payload.fir_of("SC-P1 FIR PUNTA ARENAS Zona") == "PUNTA ARENAS"
    assert payload.fir_of("SC-P1 Zona sin region") == ""
    features = body(login_as(VIEW).get(DATA))["features"]
    assert {f["fir"] for f in features if f["code"] == "SC-R54"} == {"SINTETICO"}


# ── near/ ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_near_a_point_inside_a_zone_lists_it_as_containing(snapshot):
    data = body(login_as(VIEW).get(NEAR, INSIDE_D66))
    assert [e["code"] for e in data["containing"]] == ["SC-D66"]
    assert data["point"]["lat_dms"].endswith("S") and data["point"]["lon_dms"].endswith(
        "W"
    )
    assert data["radius_km"] is None and data["touching"] == []
    assert data["near_km"] == 10.0 and data["snapshot"] == snapshot.sha256


@pytest.mark.django_db
def test_near_lists_the_three_nearest_aerodromes_with_distance_in_km_and_nm(snapshot):
    data = body(login_as(VIEW).get(NEAR, {"lat": -33.5, "lon": -70.7}))
    nearest = data["aerodromes"]
    assert [e["code"] for e in nearest][0] == "SCXA" and len(nearest) == 3
    distances = [e["distance_km"] for e in nearest]
    assert distances == sorted(distances)
    assert all(e["bearing_deg"] is not None for e in nearest)
    far = nearest[-1]
    assert far["distance_nm"] == pytest.approx(far["distance_km"] / 1.852, abs=0.02)


@pytest.mark.django_db
def test_a_circle_lists_what_it_touches_without_containing_its_centre(snapshot):
    client = login_as(VIEW)
    # El centro está fuera del triángulo SC-D66; con 12 km su borde cruza el círculo.
    outside = {"lat": -33.25, "lon": -70.45}
    plain = body(client.get(NEAR, outside))
    assert plain["containing"] == [] and plain["touching"] == []
    circle = body(client.get(NEAR, {**outside, "radius_km": 12}))
    assert "SC-D66" in [e["code"] for e in circle["touching"]]
    small = body(client.get(NEAR, {**outside, "radius_km": 1}))
    assert small["touching"] == []


@pytest.mark.django_db
def test_near_only_means_the_configured_distance(snapshot, settings):
    client = login_as(VIEW)
    point = {"lat": -33.25, "lon": -70.45}  # ~6 km del borde de SC-D66
    assert "SC-D66" in [e["code"] for e in body(client.get(NEAR, point))["near"]]
    settings.AIRSPACE_NEAR_KM = 2
    assert body(client.get(NEAR, point))["near"] == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "params",
    [
        {},
        {"lat": "x", "lon": "-70"},
        {"lat": "91", "lon": "-70"},
        {"lat": "-33", "lon": "181"},
        {"lat": "nan", "lon": "0"},
        {"lat": "-33", "lon": "-70", "radius_km": "0"},
        {"lat": "-33", "lon": "-70", "radius_km": "-3"},
        {"lat": "-33", "lon": "-70", "radius_km": "99999"},
        {"lat": "-33", "lon": "-70", "radius_km": "abc"},
    ],
)
def test_near_rejects_an_invalid_point_or_radius(snapshot, params):
    response = login_as(VIEW).get(NEAR, params)
    assert response.status_code == 400 and "error" in body(response)


@pytest.mark.django_db
def test_near_does_not_list_airstrips_or_fir_lines(snapshot):
    data = body(login_as(VIEW).get(NEAR, {"lat": -33.3, "lon": -70.8, "radius_km": 50}))
    listed = {
        e["id"]
        for key in ("containing", "touching", "near", "aerodromes")
        for e in data[key]
    }
    kinds = set(
        AirspaceFeature.objects.filter(pk__in=listed).values_list("kind", flat=True)
    )
    assert kinds <= {
        "prohibited",
        "restricted",
        "danger",
        "naval",
        "aerodrome",
        "airport",
    }


# ── el buscador del cliente es el de Python ─────────────────────────────────

NODE = shutil.which("node")
QUERIES = [
    "",
    "   ",
    "SCEL",
    "scel",
    "sc r-41",
    "SC – P 30",
    "P 50",
    "R41",
    "SC-X1",
    "-33.45, -70.66",
    "-33.45 -70.66",
    "-33,5; -70,5",
    "33 26 28 S 70 39 17 W",
    "S33 26 28 W70 39 17",
    "33°26'28\"S 70°39'17\"W",
    "33.5 S, 70.5 W",
    "91, 20",
    "-33, 181",
    "33 26 70 S 70 39 17 W",
    "-33 S 70 W",
    "N33 N70",
    "33 S 70",
    "Prueba Uno",
    "pista inventada",
    "Cañón del Maipo",
    "santiago",
    "12345",
    "zona",
    "SCXA",
    "scxc",
]
ENTRIES = [
    {"id": "1", "name": "Ad. Prueba Uno SANTIAGO", "code": "SCXA"},
    {"id": "2", "name": "Ap. Prueba Dos VALPARAÍSO", "code": "SCXB"},
    {"id": "3", "name": "Pista Inventada", "code": "SCXC"},
    {"id": "4", "name": "SC - R54 FIR SINTETICO Sector Prueba", "code": "SC-R54"},
    {"id": "5", "name": "SC – P 30 Zona de prueba", "code": "SC-P30"},
    {"id": "6", "name": "Peligro sintetico", "code": "SC-R41"},
    {"id": "7", "name": "Zona de peligro", "code": "SC-D66"},
    {"id": "8", "name": "Cañón del Maipo", "code": ""},
    {"id": "9", "name": "Santiago Centro", "code": ""},
]


def _run_node(script, payload_data):
    result = subprocess.run(  # nosec B603 B607 - node local, argumentos fijos del propio test
        [NODE, "-e", script],
        input=json.dumps(payload_data),
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


NODE_SCRIPT = """
const S = require('./static/js/airspace-search.js');
let raw = '';
process.stdin.on('data', d => raw += d);
process.stdin.on('end', () => {
  const input = JSON.parse(raw);
  const out = input.queries.map(q => ({
    parse: S.parseQuery(q),
    search: S.searchIndex(q, input.entries, 20).results.map(r => [r.entry.id, r.score]),
  }));
  process.stdout.write(JSON.stringify(out));
});
"""


def _same(left, right):
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _same(left[k], right[k]) for k in left
        )
    if isinstance(left, float) or isinstance(right, float):
        return left == pytest.approx(right)
    return left == right


@pytest.mark.skipif(NODE is None, reason="Node no está instalado")
def test_the_client_search_gives_the_same_answers_as_the_python_one():
    out = _run_node(NODE_SCRIPT, {"queries": QUERIES, "entries": ENTRIES})
    for query, got in zip(QUERIES, out, strict=True):
        expected = airspace_search.parse_query(query)
        assert _same(got["parse"], expected), (query, got["parse"], expected)
        py = airspace_search.search_index(query, ENTRIES, limit=20)["results"]
        assert got["search"] == [[r["entry"]["id"], r["score"]] for r in py], query


@pytest.mark.skipif(NODE is None, reason="Node no está instalado")
@pytest.mark.parametrize(
    ("query", "kind", "expect"),
    [
        ("SCXA", "oaci", ["1"]),
        ("sc r-41", "zone", ["6"]),
        ("prueba uno", "name", ["1"]),
        ("canon maipo", "name", ["8"]),
        ("-33.45, -70.66", "coordinate", []),
        ("33 26 28 S 70 39 17 W", "coordinate", []),
        ("33 26 70 S 70 39 17 W", "invalid_coordinate", []),
    ],
)
def test_search_cases_the_screen_depends_on(query, kind, expect):
    out = _run_node(NODE_SCRIPT, {"queries": [query], "entries": ENTRIES})[0]
    assert out["parse"]["type"] == kind
    assert [pair[0] for pair in out["search"]] == expect


@pytest.mark.skipif(NODE is None, reason="Node no está instalado")
def test_a_name_query_also_finds_a_place_by_region_or_commune():
    script = """
const S = require('./static/js/airspace-search.js');
const entries = [
  {id: 'a', name: 'Ad. Uno', code: 'SCAA', places: S.normalizeText('Región Metropolitana Pudahuel')},
  {id: 'b', name: 'Ad. Dos', code: 'SCBB', places: S.normalizeText('Valparaíso Quintero')},
];
const out = S.searchFeatures('quintero', entries, 20);
process.stdout.write(JSON.stringify(out.results.map(r => [r.entry.id, r.score])));
"""
    result = subprocess.run(  # nosec B603 B607
        [NODE, "-e", script], capture_output=True, text=True, cwd=ROOT, check=True
    )
    assert json.loads(result.stdout) == [["b", 50]]


# ── lo que el script nunca hace ─────────────────────────────────────────────

MAP_JS = (ROOT / "static" / "js" / "airspace-map.js").read_text(encoding="utf-8")


def _code_only(text):
    """Quita los comentarios de bloque y de línea para mirar sólo código."""
    import re

    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def test_the_script_only_puts_fixed_svg_through_innerhtml():
    code = _code_only(MAP_JS)
    # LV-367: los íconos son nodos `<use>` del sprite de la plantilla; ya no hay ningún `innerHTML`.\n    assert code.count("innerHTML") == 0
    assert "document.write" not in code and "eval(" not in code
    assert "insertAdjacentHTML" not in code


def test_leaflet_labels_are_always_dom_nodes_never_strings():
    """Leaflet mete un string de `bindTooltip`/`bindPopup` con `innerHTML`: con nombres de la fuente
    importada eso es XSS. Todo rótulo se pasa como nodo (`tipNode(...)`)."""
    import re

    code = _code_only(MAP_JS)
    calls = re.findall(r"\.bind(?:Tooltip|Popup)\(\s*([^,)]*)", code)
    assert calls, "el script debería rotular algo"
    for first_argument in calls:
        assert first_argument.startswith("tipNode("), first_argument
    assert ".setContent(" not in code and ".setTooltipContent(" not in code


def test_the_script_makes_no_calls_outside_its_own_origin():
    code = _code_only(MAP_JS)
    assert "http://" not in code.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in code
    assert "XMLHttpRequest" not in code and "WebSocket" not in code
    # data.json, near/, own-layers.json (E3, al encender una capa) y, desde LV-367, admin.json (al
    # encender la capa administrativa) y admin/<código>/contains (al elegir una comuna o región).
    assert code.count("fetch(") == 5


def test_the_script_never_converts_the_sources_limits_or_decides():
    code = _code_only(MAP_JS).lower()
    for forbidden in ("parsefloat(entry.vertical", "can fly", "puede volar", "buffer"):
        assert forbidden not in code
    assert "entry.vertical" in code and "textcontent" in code


def test_the_search_module_has_no_dom_and_no_visible_text():
    source = _code_only(
        (ROOT / "static" / "js" / "airspace-search.js").read_text(encoding="utf-8")
    )
    assert "document." not in source and "innerHTML" not in source
