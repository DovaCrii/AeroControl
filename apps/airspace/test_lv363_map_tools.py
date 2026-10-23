"""LV-363: the airspace map stayed dead on the real DGAC map, and its tools with it.

The real KML has a `MultiGeometry` (SC-P29: the zone and its label point). It was stored as a
`GeometryCollection`, `feature_payload` served only `coordinates` (so `null`), Leaflet threw while drawing
and the one `catch` of the script answered «the map data could not be loaded» without leaving a trace:
no filters, no results, no fiche. The synthetic KML has no `MultiGeometry`, which is why the demo worked.

These tests use that shape (built in the test, never the DGAC file: its license is not confirmed and the
repo is public) and run the real `airspace-map.js` in Node against a stub of Leaflet that throws the way
Leaflet does on a geometry without coordinates.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import translation

from apps.airspace import payload
from apps.airspace.models import AirspaceFeature
from apps.core.testing import login_as
from apps.geo.airspace_geometry import bbox_of, nearby

ROOT = Path(__file__).resolve().parents[2]
KML = Path(__file__).parent / "test_data" / "synthetic_airspace.kml"
NODE = shutil.which("node")
DATA = reverse("airspace-data")
NEAR = reverse("airspace-near")

# A zone and its label point, as the real SC-P29 arrives (lon, lat).
RING = [[-70.5, -33.3], [-70.3, -33.3], [-70.4, -33.1], [-70.5, -33.3]]
COLLECTION = {
    "type": "GeometryCollection",
    "geometries": [
        {"type": "Point", "coordinates": [-70.4, -33.2]},
        {"type": "Polygon", "coordinates": [RING]},
    ],
}


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


@pytest.fixture
def collection_zone(db):
    call_command("import_airspace_zones", "--file", str(KML), verbosity=0)
    zone = AirspaceFeature.objects.get(code="SC-D66")
    zone.geometry = COLLECTION
    zone.save(update_fields=["geometry"])
    return zone


def served(client):
    return json.loads(client.get(DATA).content)["features"]


# ── the server ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_geometry_collection_travels_with_its_parts_not_with_null_coordinates(
    collection_zone,
):
    client = login_as("view_airspacefeature")
    zone = next(f for f in served(client) if f["code"] == "SC-D66")
    geometry = zone["geometry"]
    assert geometry["type"] == "GeometryCollection"
    assert "coordinates" not in geometry
    assert [part["type"] for part in geometry["geometries"]] == ["Point", "Polygon"]
    assert all(part["coordinates"] for part in geometry["geometries"])


@pytest.mark.django_db
def test_no_served_geometry_is_ever_empty(collection_zone):
    """The invariant behind the bug: whatever the shape, a feature either has no geometry or it is drawable."""

    def drawable(geometry):
        if geometry["type"] == "GeometryCollection":
            return bool(geometry["geometries"]) and all(
                drawable(g) for g in geometry["geometries"]
            )
        return bool(geometry.get("coordinates"))

    for feature in served(login_as("view_airspacefeature")):
        assert "geometry" not in feature or drawable(feature["geometry"]), feature[
            "name"
        ]


def test_the_parts_of_a_collection_count_for_the_bbox_and_the_distance():
    assert bbox_of(COLLECTION) == (-70.5, -33.3, -70.3, -33.1)
    found = nearby(
        -33.2,
        -70.4,
        [
            {
                "properties": {
                    "id": "z",
                    "kind": "prohibited",
                    "code": "SC-P29",
                    "name": "z",
                },
                "geometry": COLLECTION,
            }
        ],
    )
    assert [e["feature"]["properties"]["id"] for e in found["containing"]] == ["z"]


@pytest.mark.django_db
def test_near_finds_a_zone_that_is_a_collection(collection_zone):
    client = login_as("view_airspacefeature")
    data = json.loads(client.get(NEAR, {"lat": -33.2, "lon": -70.42}).content)
    assert [e["code"] for e in data["containing"]] == ["SC-D66"]


def test_public_geometry_rounds_every_part():
    odd = {
        "type": "GeometryCollection",
        "geometries": [
            {"type": "Point", "coordinates": [-70.123456789, -33.987654321]}
        ],
    }
    assert payload.public_geometry(odd)["geometries"][0]["coordinates"] == [
        -70.12346,
        -33.98765,
    ]


# ── the script, in Node, against a Leaflet that is as strict as the real one ──

NODE_SCRIPT = r"""
const fs = require('fs');
let raw = '';
process.stdin.on('data', d => raw += d);
process.stdin.on('end', async () => {
  const input = JSON.parse(raw);
  const tick = async () => { for (let i = 0; i < 8; i += 1) { await new Promise(r => setImmediate(r)); } };

  function makeEnv(fetchPlan) {
    const errors = [];
    const drawn = [];
    const nodes = {};
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
    const layer = () => {
      const l = { options: {}, on() { return l; }, addTo() { return l; }, bindTooltip() { return l; },
        setLatLngs() {}, setStyle() {}, eachLayer() {}, bringToFront() {} };
      return l;
    };
    const check = (g) => {
      if (!g || typeof g !== 'object') { throw new TypeError('Invalid GeoJSON object.'); }
      if (g.type === 'GeometryCollection') { g.geometries.forEach(check); return; }
      if (JSON.stringify(g.coordinates).includes('boom')) { throw new Error('boom'); }
      if (!Array.isArray(g.coordinates) || !g.coordinates.length) {
        throw new TypeError("Cannot read properties of undefined (reading 'length')");
      }
    };
    const map = { on() { return map; }, getSize: () => ({ x: 500, y: 400 }), fitBounds() {}, setView() {},
      addLayer() {}, removeLayer() {}, getZoom: () => 5, doubleClickZoom: { enable() {}, disable() {} } };
    const L = {
      map: () => map, canvas: () => ({}), svg: () => ({ _container: stub() }), tileLayer: layer,
      control: { layers: () => layer() }, marker: layer, circleMarker: layer, polyline: layer,
      circle: layer, layerGroup: layer, divIcon: o => o, DomEvent: { stopPropagation() {} },
      geoJSON(geometry) { check(geometry); drawn.push(geometry.type); return layer(); },
    };
    const window = {
      L, AirspaceSearch: require('./static/js/airspace-search.js'), location: { search: '' },
      console: { error: (...a) => errors.push(a.join(' ')) },
      setTimeout, clearTimeout,
    };
    window.location.reload = () => { window.reloaded = true; };
    const fetch = async () => {
      const step = fetchPlan.shift();
      if (step === 'fail') { throw new TypeError('Failed to fetch'); }
      if (step === 'http') { return { ok: false, status: 500, json: async () => ({}) }; }
      return { ok: true, status: 200, json: async () => step };
    };
    class MutationObserver { observe() {} }
    const run = new Function('window', 'document', 'L', 'fetch', 'MutationObserver',
      'getComputedStyle', 'console', fs.readFileSync('./static/js/airspace-map.js', 'utf8'));
    run(window, document, L, fetch, MutationObserver, () => ({ getPropertyValue: () => '' }), window.console);
    return { errors, drawn, nodes, window };
  }

  const out = {};
  // 1. what the server now sends: draws, no error, no failure message.
  let env = makeEnv([input.data]);
  await tick();
  out.served = { drawn: env.drawn, errors: env.errors, status: env.nodes['air-status'].textContent };

  // 2. the old shape (`coordinates: null`): one entry may fail, the map and the list must not.
  env = makeEnv([input.legacy]);
  await tick();
  out.legacy = { drawn: env.drawn, errors: env.errors, status: env.nodes['air-status'].textContent };

  // 3. the network fails: the cause is logged, the message is shown and «Retry» works.
  env = makeEnv(['fail', input.data]);
  await tick();
  const retry = env.nodes['air-retry'];
  out.failed = { errors: env.errors.slice(), status: env.nodes['air-status'].textContent, retryHidden: retry.hidden };
  retry.listeners.click[0]();
  await tick();
  out.retried = { status: env.nodes['air-status'].textContent, retryHidden: retry.hidden };

  // 4. an HTTP error says which one.
  env = makeEnv(['http']);
  await tick();
  out.http = { errors: env.errors, status: env.nodes['air-status'].textContent };

  // 5. an answer that is not the expected shape (`null`) is an error too, not a silent success.
  env = makeEnv([null]);
  await tick();
  out.shape = { errors: env.errors, status: env.nodes['air-status'].textContent };
  process.stdout.write(JSON.stringify(out));
});
"""


@pytest.fixture
def node_run(collection_zone):
    if NODE is None:
        pytest.skip("Node no está instalado")
    from apps.airspace.views import tab_config

    cfg = tab_config(None)
    cfg["i18n"].update(
        loadFailed="LOAD_FAILED", resultsCount="{n} results", noResults="NONE"
    )
    cfg["tileProviders"] = []
    data = json.loads(login_as("view_airspacefeature").get(DATA).content)
    legacy = json.loads(json.dumps(data))
    for feature in legacy["features"]:
        if feature["code"] == "SC-D66":
            feature["geometry"] = {"type": "LineString", "coordinates": [["boom"]]}
        if feature["code"] == "SC-R54":
            feature["geometry"] = {"type": "GeometryCollection", "coordinates": None}
    result = subprocess.run(  # nosec B603 B607 - node local, argumentos fijos del propio test
        [NODE, "-e", NODE_SCRIPT],
        input=json.dumps({"cfg": cfg, "data": data, "legacy": legacy}),
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


def test_the_map_draws_a_zone_that_is_a_collection_without_failing(node_run):
    served_run = node_run["served"]
    assert "GeometryCollection" in served_run["drawn"]
    assert served_run["errors"] == []
    assert served_run["status"].endswith("results")


def test_one_undrawable_zone_cannot_take_the_whole_map_down(node_run):
    legacy = node_run["legacy"]
    # The list and the filters still start, and the failure is named in the console.
    assert legacy["status"].endswith("results")
    assert legacy["status"] != "LOAD_FAILED"
    assert any(line.startswith("airspace-map: draw ") for line in legacy["errors"])
    # A collection with no usable parts (the old `coordinates: null`) is skipped without an error.
    assert len(legacy["errors"]) == 1


def test_a_failed_load_logs_its_cause_shows_the_message_and_retries(node_run):
    failed = node_run["failed"]
    assert failed["status"] == "LOAD_FAILED" and failed["retryHidden"] is False
    assert any("Failed to fetch" in line for line in failed["errors"])
    retried = node_run["retried"]
    assert retried["status"].endswith("results") and retried["retryHidden"] is True


def test_an_http_error_and_an_unexpected_answer_are_named_in_the_console(node_run):
    assert any("500" in line for line in node_run["http"]["errors"])
    assert node_run["http"]["status"] == "LOAD_FAILED"
    assert any("unexpected data shape" in line for line in node_run["shape"]["errors"])
    assert node_run["shape"]["status"] == "LOAD_FAILED"


@pytest.mark.django_db
def test_the_page_has_the_retry_button_hidden_until_a_load_fails(
    collection_zone, settings
):
    settings.WEATHER_ENABLED = False
    settings.WEATHER_DEFAULT_LABEL = ""
    html = (
        login_as("view_airspacefeature").get(reverse("airspace-map")).content.decode()
    )
    assert 'id="air-retry"' in html
    assert re.search(r'id="air-retry"[^>]*\bhidden\b', html)
