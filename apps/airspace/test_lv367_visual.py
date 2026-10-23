"""LV-367 (fase 5): lo visual del mapa de espacio aéreo, medido y no sólo mirado.

* El contraste de los tokens `--id-air-*` se CALCULA con la fórmula WCAG sobre los hex del CSS (no se lee de
  un navegador): trazo/halo >= 3, halo/blanco >= 3 y trazo/negro >= 3, así que el trazo se ve sobre el
  extremo claro y el extremo oscuro de cualquier tesela.
* El script real (`airspace-map.js`) corre en Node contra un Leaflet de mentira que REGISTRA lo que se
  crea: doble trazo (halo 4 px en su panel + línea 2 px con patrón), rótulos desde el zoom 9, pistas desde
  el zoom 8 con halo, y la jerarquía de tamaños de los marcadores.
* La plantilla: leyenda plegable, ficha en tarjetas, fila de fuente y franja de conteos con íconos.
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

from apps.airspace.models import AirspaceFeature
from apps.core.testing import login_as as _login_as

ROOT = Path(__file__).resolve().parents[2]
KML = Path(__file__).parent / "test_data" / "synthetic_airspace.kml"
CSS = (ROOT / "static" / "css" / "airspace.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "js" / "airspace-map.js").read_text(encoding="utf-8")
NODE = shutil.which("node")
DATA = reverse("airspace-data")
PAGE = reverse("airspace-map")


def login_as(*codenames, lang="en"):
    client = _login_as(*codenames)
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = lang
    return client


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


@pytest.fixture
def snapshot(db, settings):
    settings.WEATHER_ENABLED = False
    settings.WEATHER_DEFAULT_LABEL = ""
    call_command("import_airspace_zones", "--file", str(KML), verbosity=0)


# ── contraste, calculado ────────────────────────────────────────────────────


def _token(name):
    return re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", CSS).group(1)


def _luminance(hex_color):
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


LINES = ("prohibited", "restricted", "danger", "naval", "fir")


@pytest.mark.parametrize("name", LINES)
def test_each_zone_line_reads_against_its_halo_and_the_darkest_tile(name):
    line = _token(f"id-air-line-{name}")
    assert contrast(line, _token("id-air-halo")) >= 3
    assert contrast(line, "#000000") >= 3


def test_the_halo_reads_against_the_lightest_tile():
    assert contrast(_token("id-air-halo"), "#ffffff") >= 3


def test_the_four_zone_colours_are_all_different():
    colours = {_token(f"id-air-line-{name}") for name in LINES[:4]}
    assert len(colours) == 4


def test_the_label_halo_and_the_airstrip_dot_are_legible():
    assert contrast("#ffffff", _token("id-air-halo")) >= 7  # code label
    assert contrast(_token("id-air-dot"), _token("id-air-halo")) >= 7  # airstrip


# ── el CSS ──────────────────────────────────────────────────────────────────


def test_the_pattern_has_no_background_and_its_marks_sit_between_25_and_35_percent():
    assert re.search(r"\.air-pat-bg\s*\{\s*fill:\s*none", CSS)
    opacity = float(
        re.search(r"\.air-pat-mark\s*\{\s*opacity:\s*([\d.]+)", CSS).group(1)
    )
    assert 0.25 <= opacity <= 0.35
    for rule in re.findall(r"\.air-pat--\w+[^{]*\{[^}]*\}", CSS):
        assert "-bg" not in rule  # nada de `--sev-*-bg` turbio bajo el patrón


def test_the_selected_zone_gets_a_solid_twelve_percent_fill_in_its_own_colour():
    for kind in ("prohibited", "restricted", "danger", "naval"):
        rule = re.search(
            rf"\.air-shape--{kind}\.is-selected\s*\{{([^}}]*)\}}", CSS
        ).group(1)
        assert f"var(--id-air-line-{kind})" in rule and "fill-opacity: 0.12" in rule


def test_the_halo_pane_sits_below_the_lines_and_the_attribution_has_a_surface():
    assert re.search(r"\.air-map \.leaflet-airHalo-pane\s*\{\s*z-index:\s*399", CSS)
    attribution = re.search(r"\.leaflet-control-attribution\s*\{([^}]*)\}", CSS).group(
        1
    )
    assert "90%" in attribution and "--ac-surface" in attribution


def test_the_css_never_leans_on_the_base_tokens_without_a_fallback():
    for token in ("--id-edge", "--id-tile"):
        for use in re.findall(rf"var\({token}[^)]*\)", CSS):
            assert "," in use, use


def test_the_css_carries_no_inline_style_hooks_for_the_csp():
    assert "style=" not in CSS


def test_the_focus_of_every_interactive_piece_is_visible():
    for selector in (
        ".air-fiche:focus-visible",
        ".air-legend-summary:focus-visible",
        ".air-row:focus-visible",
    ):
        assert selector in CSS


# ── la plantilla ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_page_has_a_foldable_legend_and_the_sheet_in_cards(snapshot):
    html = login_as("view_airspacefeature").get(PAGE).content.decode()
    assert re.search(r'<details class="air-legend" id="air-legend" open>', html)
    assert "air-i-layers" in html and "Aeronautical" in html
    for title in ("Vertical limits", "Schedule", "Source text"):
        assert re.search(rf"</svg>{title}</dt>", html), title
    assert 'id="air-f-region"' in html and 'id="air-f-commune"' in html
    assert re.search(
        r'<article id="air-fiche"[^>]*tabindex="0"', html
    )  # Tab llega a la ficha
    assert "exactly as the source wrote them" in html


@pytest.mark.django_db
def test_the_source_row_is_legible_and_fresh_or_stale_with_symbol_and_word(snapshot):
    client = login_as("view_airspacefeature")
    html = client.get(PAGE).content.decode()
    row = re.search(r'<p class="air-source[^"]*">.*?</p>', html, re.S).group(0)
    from apps.airspace.models import AirspaceSnapshot as Snap

    name = Snap.objects.get(is_current=True).source_name
    assert re.search(rf"<strong>.*{re.escape(name)}.*</strong>", row, re.S)
    assert "Licence: not confirmed" in row and "Up to date" in row and "●" in row
    from datetime import timedelta

    from django.utils import timezone

    from apps.airspace.models import AirspaceSnapshot

    AirspaceSnapshot.objects.update(fetched_at=timezone.now() - timedelta(days=45))
    stale = client.get(PAGE).content.decode()
    assert "45 days old" in stale and "air-fresh--stale" in stale and "▲" in stale


@pytest.mark.django_db
def test_every_kind_has_an_icon_in_the_sprite_and_in_the_counts(snapshot):
    html = login_as("view_airspacefeature").get(PAGE).content.decode()
    kinds = [kind for kind, _label in AirspaceFeature.KIND_CHOICES if kind != "aux"]
    for kind in kinds:
        assert f'id="air-i-{kind}"' in html, kind
        assert f'href="#air-i-{kind}"' in html, kind
    # Un símbolo del sprite no lleva atributos de estilo en línea (CSP).
    sprite = re.search(r'<svg class="air-sprite".*?</svg>', html, re.S).group(0)
    assert "style=" not in sprite


@pytest.mark.django_db
def test_the_page_is_translated_to_spanish_in_the_new_pieces(snapshot):
    html = login_as("view_airspacefeature", lang="es").get(PAGE).content.decode()
    for text in (
        "Aeronáutico",
        "Límites verticales",
        "Horario",
        "Texto de la fuente",
        "Licencia: no confirmada",
        "Al día",
        "Fuente de los datos",
    ):
        assert text in html, text


# ── el script, en Node, contra un Leaflet que registra lo que se crea ────────

NODE_SCRIPT = r"""
const fs = require('fs');
let raw = '';
process.stdin.on('data', d => raw += d);
process.stdin.on('end', async () => {
  const input = JSON.parse(raw);
  const tick = async () => { for (let i = 0; i < 8; i += 1) { await new Promise(r => setImmediate(r)); } };

  async function run(zoom) {
    const created = [];
    const onMap = new Set();
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
    const make = (kind, extra) => (a, b) => {
      const l = Object.assign({ kind, options: (kind === 'geoJSON' ? b : b) || {}, args: a,
        on() { return l; }, bindTooltip() { return l; }, setLatLngs() {}, setStyle() {}, eachLayer() {},
        bringToFront() {} }, extra ? extra(a, b) : {});
      l.addTo = () => { onMap.add(l); return l; };
      created.push(l);
      return l;
    };
    const map = { on() { return map; }, getSize: () => ({ x: 500, y: 400 }), fitBounds() {}, setView() {},
      addLayer() {}, removeLayer(l) { onMap.delete(l); }, createPane() {}, getZoom: () => zoom,
      doubleClickZoom: { enable() {}, disable() {} } };
    const L = {
      map: () => map, canvas: () => ({ tag: 'canvas' }),
      svg: o => ({ tag: (o && o.pane) || 'overlay', _container: stub() }),
      tileLayer: make('tile'), control: { layers: make('control') },
      marker: make('marker'), circleMarker: make('circleMarker'), polyline: make('polyline'),
      circle: make('circle'), layerGroup: make('group'), divIcon: o => o, DomEvent: { stopPropagation() {} },
      geoJSON: make('geoJSON', (g, o) => ({ style: o.style({ geometry: g }) })),
    };
    const window = {
      L, AirspaceSearch: require('./static/js/airspace-search.js'), location: { search: '' },
      console: { error: () => {} }, setTimeout, clearTimeout,
    };
    class MutationObserver { observe() {} }
    const code = fs.readFileSync('./static/js/airspace-map.js', 'utf8');
    new Function('window', 'document', 'L', 'fetch', 'MutationObserver', 'getComputedStyle', 'console', code)(
      window, document, L, async () => ({ ok: true, status: 200, json: async () => input.data }),
      MutationObserver, () => ({ getPropertyValue: () => '' }), window.console);
    await tick();
    return created.map(l => ({
      kind: l.kind, on: onMap.has(l), minZoom: l.airMinZoom || 0, role: l.airRole || null,
      cls: l.options.icon ? l.options.icon.className : (l.options.className || null),
      size: l.options.icon ? l.options.icon.iconSize : null,
      anchor: l.options.icon ? l.options.icon.iconAnchor : null,
      radius: l.options.radius || null, weight: l.options.weight == null ? null : l.options.weight,
      style: l.style || null, renderer: l.options.renderer ? l.options.renderer.tag : null,
      interactive: l.options.interactive, fill: l.options.fillColor || null,
    }));
  }

  const out = {};
  for (const zoom of [5, 8, 9]) { out['z' + zoom] = await run(zoom); }
  process.stdout.write(JSON.stringify(out));
});
"""


@pytest.fixture
def node_run(snapshot):
    if NODE is None:
        pytest.skip("Node no está instalado")
    from apps.airspace.views import tab_config

    cfg = tab_config(None)
    cfg["tileProviders"] = []
    data = json.loads(login_as("view_airspacefeature").get(DATA).content)
    result = subprocess.run(  # nosec B603 B607 - node local, argumentos fijos del propio test
        [NODE, "-e", NODE_SCRIPT],
        input=json.dumps({"cfg": cfg, "data": data}),
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


def _of(layers, **match):
    return [
        layer for layer in layers if all(layer.get(k) == v for k, v in match.items())
    ]


def test_every_zone_is_drawn_twice_a_four_pixel_halo_under_a_two_pixel_line(node_run):
    layers = node_run["z9"]
    halos = _of(layers, kind="geoJSON", role="halo")
    lines = _of(layers, kind="geoJSON", role="line")
    assert halos and len(halos) == len(lines)
    for halo in halos:
        assert (
            halo["renderer"] == "airHalo"
        )  # su propio panel, debajo de todas las líneas
        assert halo["style"]["weight"] == 4 and halo["style"]["className"] == "air-halo"
        assert halo["style"]["interactive"] is False
    for line in lines:
        assert line["renderer"] == "overlay" and line["style"]["weight"] == 2
        assert line["style"]["className"].startswith("air-shape air-shape--")
    patterned = [ln for ln in lines if ln["style"].get("fill")]
    assert patterned and all(
        ln["style"]["fillColor"].startswith("url(#air-pat-") for ln in patterned
    )


def test_codes_appear_from_zoom_nine_and_never_before(node_run):
    for zoom, expected in (("z5", False), ("z8", False), ("z9", True)):
        tags = _of(node_run[zoom], kind="marker", cls="air-tag-wrap")
        assert tags, zoom
        assert all(tag["minZoom"] == 9 for tag in tags)
        assert any(tag["on"] for tag in tags) is expected, zoom
        assert all(tag["interactive"] is False for tag in tags)


def test_airstrips_have_radius_four_with_a_halo_and_appear_from_zoom_eight(node_run):
    for zoom, expected in (("z5", False), ("z8", True)):
        dots = _of(node_run[zoom], kind="circleMarker", radius=4)
        halos = _of(node_run[zoom], kind="circleMarker", radius=6.5)
        assert dots and halos and len(dots) == len(halos)
        assert all(d["on"] is expected for d in dots + halos), zoom
        assert all(h["interactive"] is False for h in halos)


def test_marker_hierarchy_airport_thirty_aerodrome_and_badge_twenty_two(node_run):
    icons = {
        layer["cls"]: layer["size"]
        for layer in node_run["z9"]
        if layer["kind"] == "marker" and layer["size"]
    }
    sizes = {
        layer["size"][0] for layer in node_run["z9"] if layer["cls"] == "air-plane-wrap"
    }
    assert sizes == {30, 22}
    assert icons["air-badge-wrap"] == [22, 22]


# ── guardianes del script ───────────────────────────────────────────────────


def test_the_labels_are_dom_nodes_and_the_script_adds_no_network_call():
    code = re.sub(r"/\*.*?\*/", "", JS, flags=re.S)
    assert (
        "html: node" in code
    )  # el rótulo es un nodo, no un string con datos de la fuente
    # data.json, near/, own-layers.json y, desde la fase 7, admin.json y admin/<código>/contains.
    assert code.count("fetch(") == 5
    assert "innerHTML" not in code


def test_escape_still_ends_a_tool():
    assert re.search(r'event\.key === "Escape" && tool', JS)
