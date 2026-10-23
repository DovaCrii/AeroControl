"""LV-367 (fase 7): la capa «Límites administrativos» en la pantalla de espacio aéreo, probada de verdad.

El script real (`airspace-map.js`) corre en Node contra un Leaflet de mentira que REGISTRA lo que se crea y
un DOM mínimo que conserva el árbol (etiqueta, clase, hijos, texto), con la capa y los datos REALES de BCN
y el `contains` que sirve la vista. Lo que se afirma:

* con la capa apagada no hay ninguna petición administrativa (sólo `data.json`);
* encenderla pide `admin.json` UNA vez por nivel (LOD 1 con zoom <= 7, LOD 2 con zoom >= 8), la dibuja en
  lienzo con halo, y los colores se leen de variables CSS y se releen al cambiar el tema;
* los nombres: regiones desde el zoom 5 y comunas desde el 9;
* elegir una comuna/región (la búsqueda no distingue tildes ni mayúsculas) encuadra, realza (comuna: halo,
  línea de 3 px y relleno del 12 %; región: sus comunas rellenas sin trazo interno) y lista, en una lista
  accesible, lo que contiene o toca;
* los errores dejan su causa en la consola (`airspace-map: <dónde>: <mensaje>`) y hay «Reintentar».
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

from apps.core.testing import login_as
from apps.geo import administrative_layer as layer
from apps.geo.administrative import locate

ROOT = Path(__file__).resolve().parents[2]
KML = Path(__file__).parent / "test_data" / "synthetic_airspace.kml"
JS = (ROOT / "static" / "js" / "airspace-map.js").read_text(encoding="utf-8")
NODE = shutil.which("node")


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


NODE_SCRIPT = r"""
const fs = require('fs');
let raw = '';
process.stdin.on('data', d => raw += d);
process.stdin.on('end', async () => {
  const input = JSON.parse(raw);
  const tick = async (n) => { for (let i = 0; i < (n || 12); i += 1) { await new Promise(r => setImmediate(r)); } };

  function makeEnv(plan) {
    const state = { zoom: plan.zoom, css: Object.assign({}, plan.css || {}), adminFailures: plan.adminFailures || 0,
      containsFails: plan.containsFails || 0 };
    const log = { fetches: [], errors: [], layers: [], fits: [], removed: [] };
    const all = [];
    const nodes = {};
    const onMap = new Set();
    function mk(tag) {
      const e = { tag, className: '', dataset: {}, style: {}, children: [], listeners: {}, attrs: {}, hidden: false,
        checked: false, value: '', _text: '', classList: { toggle() {}, add() {}, remove() {} },
        appendChild(c) { this.children.push(c); return c; }, insertBefore() {},
        setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; }, focus() {},
        addEventListener(n, f) { (this.listeners[n] = this.listeners[n] || []).push(f); },
        closest() { return null; }, querySelector() { return null; },
        querySelectorAll(sel) {
          const wanted = sel.replace('.', ''); const out = [];
          const walk = n => (n.children || []).forEach(c => {
            if (String(c.className || '').split(' ').includes(wanted)) { out.push(c); }
            walk(c);
          });
          walk(this); return out;
        } };
      Object.defineProperty(e, 'textContent', { get() { return e._text; },
        set(v) { e._text = v; if (v === '') { e.children = []; } } });
      all.push(e);
      return e;
    }
    const document = {
      getElementById(id) {
        if (id === 'air-config') { return { textContent: JSON.stringify(input.cfg) }; }
        return nodes[id] = nodes[id] || mk('div');
      },
      createElement: mk, createElementNS: (ns, tag) => mk(tag),
      querySelector(sel) {
        return sel === '[data-admin]' ? all.find(e => e.dataset && e.dataset.admin) || null : null;
      },
      addEventListener(n, f) { (document.listeners[n] = document.listeners[n] || []).push(f); },
      listeners: {}, documentElement: mk('html'),
    };
    const make = (kind) => (a, b) => {
      const l = { kind, args: a, options: b || {}, on() { return l; }, bindTooltip() { return l; }, setLatLngs() {},
        eachLayer() {}, bringToFront() {},
        setStyle(s) { log.layers.push({ restyle: true, role: l.airRole || null, style: s }); } };
      l.addTo = () => { onMap.add(l); return l; };
      log.layers.push(l);
      return l;
    };
    const handlers = {};
    const map = {
      on(ev, fn) { (handlers[ev] = handlers[ev] || []).push(fn); return map; },
      getSize: () => ({ x: 500, y: 400 }), fitBounds(b) { log.fits.push(b); }, setView() {}, addLayer() {},
      removeLayer(l) { onMap.delete(l); log.removed.push(l); }, createPane() {}, getZoom: () => state.zoom,
      doubleClickZoom: { enable() {}, disable() {} },
    };
    const L = {
      map: () => map, canvas: o => ({ tag: 'canvas', pane: (o && o.pane) || null }),
      svg: o => ({ tag: 'svg', pane: (o && o.pane) || null, _container: mk('svg') }),
      tileLayer: make('tile'), control: { layers: make('control') }, marker: make('marker'),
      circleMarker: make('circleMarker'), polyline: make('polyline'), polygon: make('polygon'),
      circle: make('circle'), layerGroup: make('group'), divIcon: o => o, DomEvent: { stopPropagation() {} },
      geoJSON: make('geoJSON'),
    };
    let observerCallback = null;
    class MutationObserver { constructor(cb) { observerCallback = cb; } observe() {} }
    const window = {
      L, AirspaceSearch: require('./static/js/airspace-search.js'), location: { search: '' },
      console: { error: (...a) => log.errors.push(a.join(' ')) }, setTimeout, clearTimeout,
    };
    const answer = (body) => ({ ok: true, status: 200, json: async () => body });
    const fetch = async (url) => {
      log.fetches.push(url);
      if (url.includes('data.json')) { return answer(input.data); }
      if (url.includes('admin.json')) {
        if (state.adminFailures > 0) { state.adminFailures -= 1; return { ok: false, status: 500, json: async () => ({}) }; }
        return answer(url.includes('lod=2') ? input.admin2 : input.admin1);
      }
      if (url.includes('/contains')) {
        if (state.containsFails > 0) { state.containsFails -= 1; throw new TypeError('Failed to fetch'); }
        return answer(input.contains);
      }
      return answer({ items: [] });
    };
    const code = fs.readFileSync('./static/js/airspace-map.js', 'utf8');
    new Function('window', 'document', 'L', 'fetch', 'MutationObserver', 'getComputedStyle', 'console', code)(
      window, document, L, fetch, MutationObserver,
      () => ({ getPropertyValue: name => state.css[name] || '' }), window.console);
    return { state, log, nodes, document, map, handlers, onMap, all, observer: () => observerCallback() };
  }

  const summary = (layerObj) => ({ kind: layerObj.kind, role: layerObj.airRole || null,
    pane: layerObj.options.renderer ? layerObj.options.renderer.pane : null, weight: layerObj.options.weight,
    color: layerObj.options.color, stroke: layerObj.options.stroke, fillOpacity: layerObj.options.fillOpacity,
    fill: layerObj.options.fill, interactive: layerObj.options.interactive,
    cls: layerObj.options.icon ? layerObj.options.icon.className : null, minZoom: layerObj.airMinZoom || 0,
    on: false });
  const withOn = (env, list) => list.filter(l => !l.restyle).map(l => Object.assign(summary(l), { on: env.onMap.has(l) }));
  const adminBox = env => env.all.find(e => e.dataset && e.dataset.admin);
  const onlyAdmin = list => list.filter(l => /admin/i.test(String(l.role)) || l.cls === 'air-admin-tag-wrap');
  const typeQuery = async (env, text) => {
    env.nodes['air-q'].value = text;
    env.nodes['air-q'].listeners.input[0]();
    await new Promise(r => setTimeout(r, 220)); await tick();
  };
  const rows = env => env.nodes['air-results'].children.map(li => li.children[0]);
  const rowSummary = btn => ({ id: btn.dataset.id, texts: btn.children.map(c => c.children.length
    ? c.children.map(x => x.textContent) : c.textContent) });
  const tree = host => host.children.map(sec => ({ tag: sec.tag, heading: sec.children[0].tag + ':' + sec.children[0].textContent,
    list: sec.children[1] ? sec.children[1].tag : null,
    items: sec.children[1] && sec.children[1].tag === 'ul' ? sec.children[1].children.map(li =>
      li.tag + '>' + li.children.map(b => b.tag + ':' + b.type + ':' + (b.dataset.id ? 'id' : '-')).join(',')) : [],
    empty: sec.children[1] && sec.children[1].tag === 'p' ? sec.children[1].textContent : null }));

  const out = {};

  // A. capa apagada: ninguna petición administrativa, ni al buscar; la búsqueda entiende comunas y regiones.
  let env = makeEnv({ zoom: 5 }); await tick();
  out.off = { fetches: env.log.fetches.slice(), admin: onlyAdmin(withOn(env, env.log.layers)).length };
  await typeQuery(env, input.queries.commune);
  out.search = { rows: rows(env).slice(0, 3).map(rowSummary), fetches: env.log.fetches.slice(),
    kinds: env.nodes['air-kind'].children.map(o => o.value) };
  await typeQuery(env, input.queries.accent);
  out.accent = rows(env).slice(0, 2).map(rowSummary);
  out.legend = { box: !!adminBox(env), checked: adminBox(env).checked, groups: env.nodes['air-legend-admin'].children.length };

  // B. encenderla: un nivel por zoom, en lienzo, con halo; nombres por zoom.
  env = makeEnv({ zoom: 5, css: { '--id-air-admin-line': '#ffffff', '--id-air-admin-halo': '#0b1220',
    '--id-air-admin-region': '#ffd166' } }); await tick();
  const box = adminBox(env); box.checked = true; box.listeners.change[0](); await tick();
  out.on5 = { fetches: env.log.fetches.filter(u => u.includes('admin')), layers: onlyAdmin(withOn(env, env.log.layers)) };
  env.state.zoom = 9; env.handlers.zoomend.forEach(f => f()); await tick();
  out.on9 = { fetches: env.log.fetches.filter(u => u.includes('admin')), layers: onlyAdmin(withOn(env, env.log.layers)) };
  env.handlers.zoomend.forEach(f => f()); await tick();
  out.again = env.log.fetches.filter(u => u.includes('admin.json')).length;
  box.checked = false; box.listeners.change[0](); await tick();
  out.off2 = withOn(env, env.log.layers).filter(l => (/^admin(Halo|Line)$/.test(String(l.role)) || l.cls === 'air-admin-tag-wrap') && l.on).length;

  // C. el tema cambia: los colores se releen.
  env = makeEnv({ zoom: 5, css: { '--id-air-admin-line': '#ffffff', '--id-air-admin-halo': '#0b1220',
    '--id-air-admin-region': '#ffd166' } }); await tick();
  const boxC = adminBox(env); boxC.checked = true; boxC.listeners.change[0](); await tick();
  env.state.css['--id-air-admin-line'] = '#101010'; env.observer();
  out.theme = env.log.layers.filter(l => l.restyle && l.role === 'adminLine').map(l => l.style.color);

  // D. elegir una comuna y una región.
  for (const [key, query] of [['commune', input.queries.commune], ['region', input.queries.region]]) {
    env = makeEnv({ zoom: 5 }); await tick();
    await typeQuery(env, query);
    const first = rows(env)[0];
    const fitsBefore = env.log.fits.length;
    env.document.listeners.click[0]({ target: { closest: () => first } });
    await tick(30);
    out[key] = {
      fetches: env.log.fetches.filter(u => u.includes('admin')),
      fits: env.log.fits.length - fitsBefore, panelHidden: env.nodes['air-admin-out'].hidden,
      name: env.nodes['air-admin-name'].textContent, status: env.nodes['air-admin-status'].textContent,
      note: env.nodes['air-admin-note'].textContent, tree: tree(env.nodes['air-admin-lists']),
      highlight: env.log.layers.filter(l => !l.restyle && /Highlight/.test(String(l.airRole)) && env.onMap.has(l)).map(summary),
      fiche: [env.nodes['air-fiche-empty'].hidden, env.nodes['air-fiche-body'].hidden],
      current: env.nodes['air-results'].querySelectorAll('.air-row').filter(r => r.attrs['aria-current']).length,
      checked: adminBox(env).checked,
    };
  }
  // y «Limpiar» lo quita todo.
  env.nodes['air-tool-clear'].listeners.click[0](); await tick();
  out.cleared = { hidden: env.nodes['air-admin-out'].hidden, lists: env.nodes['air-admin-lists'].children.length,
    removed: env.log.removed.filter(l => /Highlight/.test(String(l.airRole))).length };

  // E. fallos: la causa a la consola, el aviso y «Reintentar».
  env = makeEnv({ zoom: 5, adminFailures: 1 }); await tick();
  const boxE = adminBox(env); boxE.checked = true; boxE.listeners.change[0](); await tick();
  const retry = env.nodes['air-admin-retry'];
  out.failed = { errors: env.log.errors.slice(), checked: boxE.checked, retryHidden: retry.hidden,
    hint: env.nodes['air-tool-hint'].textContent };
  retry.listeners.click[0](); await tick();
  out.retried = { fetches: env.log.fetches.filter(u => u.includes('admin.json')).length, retryHidden: retry.hidden,
    checked: boxE.checked, shown: withOn(env, env.log.layers).filter(l => /^admin(Halo|Line)$/.test(String(l.role)) && l.on).length };

  env = makeEnv({ zoom: 5, containsFails: 1 }); await tick();
  await typeQuery(env, input.queries.commune);
  env.document.listeners.click[0]({ target: { closest: () => rows(env)[0] } }); await tick(30);
  const cRetry = env.nodes['air-admin-contains-retry'];
  out.containsFailed = { errors: env.log.errors.slice(), status: env.nodes['air-admin-status'].textContent,
    retryHidden: cRetry.hidden };
  cRetry.listeners.click[0](); await tick(30);
  out.containsRetried = { status: env.nodes['air-admin-status'].textContent, retryHidden: cRetry.hidden };

  process.stdout.write(JSON.stringify(out));
});
"""


@pytest.fixture
def run(db, settings):
    if NODE is None:
        pytest.skip("Node no está instalado")
    settings.WEATHER_ENABLED = False
    settings.WEATHER_DEFAULT_LABEL = ""
    call_command("import_airspace_zones", "--file", str(KML), verbosity=0)
    from apps.airspace.views import tab_config

    client = login_as("view_airspacefeature")
    home = locate(-33.5, -70.7)  # donde cae el aeródromo sintético SCXA
    cfg = tab_config(None)
    cfg["tileProviders"] = []
    data = json.loads(client.get(reverse("airspace-data")).content)
    contains = json.loads(
        client.get(reverse("airspace-admin-contains", args=[home["code"]])).content
    )
    queries = {
        "commune": home["comuna"],
        "accent": "NUNOA" if home["comuna"] != "Ñuñoa" else "nunoa",
        "region": home["region"],
    }
    result = subprocess.run(  # nosec B603 B607 - node local, argumentos fijos del propio test
        [NODE, "-e", NODE_SCRIPT],
        input=json.dumps(
            {
                "cfg": cfg,
                "data": data,
                "admin1": layer.build_layer(1),
                "admin2": layer.build_layer(2),
                "contains": contains,
                "queries": queries,
            }
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",  # los nombres de comunas llevan tildes y eñes
        cwd=ROOT,
        timeout=120,
        check=True,
    )
    out = json.loads(result.stdout)
    out["_home"] = home
    out["_contains"] = contains
    out["_cfg"] = cfg
    return out


def test_with_the_layer_off_nothing_administrative_is_requested_or_drawn(run):
    assert [u for u in run["off"]["fetches"] if "admin" in u] == []
    assert run["off"]["admin"] == 0
    # ni siquiera al buscar una comuna: el padrón de nombres ya viene en la configuración de la página.
    assert [u for u in run["search"]["fetches"] if "admin" in u] == []
    assert run["legend"]["box"] and run["legend"]["checked"] is False


def Search_normalize(text):
    import unicodedata

    stripped = "".join(
        ch
        for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    return stripped.lower()


def test_the_search_finds_communes_and_regions_without_accents_or_capitals(run):
    home = run["_home"]
    first = run["search"]["rows"][0]
    assert first["id"] == "admin:" + home["code"]
    assert first["texts"][1][1] == home["comuna"]  # el nombre
    assert "Commune" in first["texts"][2][0]  # el tipo
    assert "commune" in run["search"]["kinds"] and "region" in run["search"]["kinds"]
    # `NUNOA` (mayúsculas y sin tilde) encuentra Ñuñoa.
    accent = run["accent"][0]
    assert accent["id"].startswith("admin:")
    assert Search_normalize(accent["texts"][1][1]) == "nunoa"


def test_switching_it_on_asks_for_one_level_by_zoom_and_draws_it_on_canvas_with_a_halo(
    run,
):
    zoom5 = run["on5"]
    assert [u.split("?")[1] for u in zoom5["fetches"]] == ["lod=1"]
    halo, line = [
        layer_
        for layer_ in zoom5["layers"]
        if layer_["role"] in ("adminHalo", "adminLine")
    ]
    assert (halo["role"], halo["pane"], halo["weight"], halo["color"]) == (
        "adminHalo",
        "airAdmin",
        3,
        "#0b1220",
    )
    assert (line["role"], line["weight"], line["color"]) == ("adminLine", 1, "#ffffff")
    assert halo["interactive"] is False and line["interactive"] is False
    assert halo["on"] and line["on"]
    # El zoom 9 pide el nivel fino, saca el liviano y no vuelve a pedir lo ya cargado.
    zoom9 = run["on9"]
    assert [u.split("?")[1] for u in zoom9["fetches"]] == ["lod=1", "lod=2"]
    active = [
        layer_
        for layer_ in zoom9["layers"]
        if layer_["role"] in ("adminHalo", "adminLine") and layer_["on"]
    ]
    assert len(active) == 2
    assert run["again"] == 2
    assert run["off2"] == 0  # apagarla saca todo


def test_region_names_show_from_zoom_five_and_commune_names_from_nine(run):
    def labels(stage):
        return [
            layer_
            for layer_ in run[stage]["layers"]
            if layer_["cls"] == "air-admin-tag-wrap"
        ]

    five = labels("on5")
    assert five and {layer_["minZoom"] for layer_ in five} == {5, 9}
    assert (
        sum(1 for layer_ in five if layer_["on"]) == 16
    )  # las regiones, y ninguna comuna
    nine = labels("on9")
    assert sum(1 for layer_ in nine if layer_["on"]) == 16 + 345
    assert {layer_["minZoom"] for layer_ in nine if layer_["on"]} == {5, 9}


def test_the_colours_are_read_from_css_and_read_again_when_the_theme_changes(run):
    assert run["theme"] and set(run["theme"]) == {"#101010"}
    assert (
        "--id-air-admin-line" in JS
        and "--id-air-admin-halo" in JS
        and "--id-air-admin-region" in JS
    )


def test_choosing_a_commune_frames_it_highlights_it_and_lists_what_it_holds(run):
    commune = run["commune"]
    home = run["_home"]
    assert commune["fits"] == 1
    # Elegirla enciende la capa (necesita la geometría) y pide el contains de ESA comuna.
    assert commune["checked"] is True
    assert any(
        u.endswith(f"/admin/{home['code']}/contains") for u in commune["fetches"]
    )
    assert commune["panelHidden"] is False and commune["name"] == home["comuna"]
    assert commune["fiche"] == [
        False,
        True,
    ]  # la ficha de una zona no se queda con la comuna anterior
    assert (
        commune["current"] == 1
    )  # la fila elegida queda marcada para quien lee con lector de pantalla
    halo = [h for h in commune["highlight"] if h["role"] == "adminHighlightHalo"]
    shape = [h for h in commune["highlight"] if h["role"] == "adminHighlight"]
    assert halo and shape and len(halo) == len(shape) == 1
    assert halo[0]["weight"] == 6 and halo[0]["color"] == "#0b1220"
    assert shape[0]["weight"] == 3 and shape[0]["fillOpacity"] == 0.12
    assert shape[0]["pane"] == "airAdmin"


def test_the_contains_list_is_an_accessible_list_with_a_heading_per_group(run):
    commune = run["commune"]
    contains = run["_contains"]
    headings = [section["heading"] for section in commune["tree"]]
    assert [h.split(":")[0] for h in headings] == ["h3", "h3", "h3"]
    assert [h.split(":")[1].rsplit(" (", 1)[0] for h in headings] == [
        "Zones inside",
        "Zones that touch it",
        "Aerodromes inside",
    ]
    for section in commune["tree"]:
        assert section["tag"] == "section"
        if section["list"] == "ul":
            # Una lista real: `ul > li > button type=button` con el id del elemento (se abre con Enter).
            assert section["items"] and all(
                item == "li>button:button:id" for item in section["items"]
            )
        else:
            assert section["empty"] == "None"  # un grupo vacío lo dice, no desaparece
    count = sum(len(s["items"]) for s in commune["tree"])
    assert count == len(contains["zones"]) + len(contains["aerodromes"]) >= 2
    assert commune["status"] == (
        f"{len(contains['zones'])} zones and {len(contains['aerodromes'])} aerodromes in {contains['area']['name']}"
    )
    assert "Referential, BCN source, within about 111 m." in commune["note"]


def test_a_region_is_highlighted_by_filling_its_communes_with_no_inner_stroke(run):
    region = run["region"]
    assert region["highlight"], "la región debe realzarse"
    assert all(
        h["role"] == "adminHighlight" for h in region["highlight"]
    )  # sin halo por comuna
    assert all(
        h["stroke"] is False and h["fillOpacity"] == 0.12 for h in region["highlight"]
    )
    assert len(region["highlight"]) == len(
        [
            c
            for c in layer.build_layer(1)["communes"]
            if c["region"] == "r" + run["_home"]["code"][:-3]
        ]
    )
    assert region["fits"] == 1 and region["name"] == run["_home"]["region"]


def test_clear_removes_the_highlight_and_the_panel(run):
    assert run["cleared"]["hidden"] is True and run["cleared"]["lists"] == 0
    assert run["cleared"]["removed"] > 0


def test_a_failed_load_names_its_cause_in_the_console_and_offers_a_retry(run):
    failed = run["failed"]
    assert "airspace-map: admin layer: admin.json answered 500" in failed["errors"]
    assert failed["checked"] is False and failed["retryHidden"] is False
    assert (
        failed["hint"]
        == "The administrative boundaries could not be loaded. Try again."
    )
    retried = run["retried"]
    assert retried["retryHidden"] is True and retried["checked"] is True
    assert retried["fetches"] == 2 and retried["shown"] == 2


def test_a_failed_contains_names_its_cause_and_retries(run):
    failed = run["containsFailed"]
    assert any(
        line.startswith("airspace-map: admin contains: Failed to fetch")
        for line in failed["errors"]
    )
    assert (
        failed["status"] == "The query failed. Try again."
        and failed["retryHidden"] is False
    )
    retried = run["containsRetried"]
    assert retried["retryHidden"] is True and "aerodromes in" in retried["status"]


# ── guardianes del script y de la plantilla ─────────────────────────────────


def _code_only(text):
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_the_script_stays_free_of_innerhtml_and_never_decides_anything():
    code = _code_only(JS)
    assert "innerHTML" not in code and "insertAdjacentHTML" not in code
    lowered = code.lower()
    for forbidden in ("can fly", "puede volar", "buffer"):
        assert forbidden not in lowered


def test_admin_labels_and_rows_are_nodes_with_text_content(run):
    # El nombre de una comuna entra con `textContent` (nodo `span`), no como HTML.
    assert re.search(
        r'el\("span", "air-admin-tag air-admin-tag--" \+ item\.kind, item\.name\)', JS
    )
    assert "html: node" in JS


def test_the_page_config_carries_the_names_but_no_geometry(run):
    cfg = run["_cfg"]
    assert cfg["adminUrl"].endswith("/admin.json")
    assert "__code__" in cfg["adminContainsUrl"]
    assert len(cfg["adminIndex"]) == 362
    assert all("rings" not in item for item in cfg["adminIndex"])
    assert cfg["kinds"]["commune"] == "Commune" and cfg["kinds"]["region"] == "Region"
    assert cfg["kinds"]["undemarcated"] == "Undemarcated zone"


@pytest.mark.django_db
def test_the_page_offers_the_administrative_group_and_says_cities_are_not_there(
    db, settings
):
    settings.WEATHER_ENABLED = False
    settings.WEATHER_DEFAULT_LABEL = ""
    call_command("import_airspace_zones", "--file", str(KML), verbosity=0)
    client = login_as("view_airspacefeature")
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "en"
    html = client.get(reverse("airspace-map")).content.decode()
    assert 'id="air-legend-admin"' in html and 'id="air-admin-retry"' in html
    assert "Cities are not available: communes are offered instead." in html
    assert re.search(
        r'<section id="air-admin-out"[^>]*aria-labelledby="air-admin-title"[^>]*hidden',
        html,
    )
    assert 'id="air-admin-status"' in html and 'role="status"' in html


# ── colores de la capa administrativa: calculados, no mirados ─────────────────


def test_the_administrative_colours_read_against_their_halo_and_both_tile_extremes():
    from apps.airspace.test_lv367_visual import _token, contrast

    halo = _token("id-air-admin-halo")
    line = _token("id-air-admin-line")
    region = _token("id-air-admin-region")
    assert region.lower() == "#ffd166"  # el ámbar del diseño aprobado
    assert line.lower() == "#ffffff"
    assert contrast(line, halo) >= 3 and contrast(region, halo) >= 3
    assert contrast(region, "#000000") >= 3  # sobre la tesela más oscura
    assert contrast(halo, "#ffffff") >= 3  # y el halo sobre la más clara


def test_the_administrative_pane_sits_below_the_halo_and_the_zones():
    css = (ROOT / "static" / "css" / "airspace.css").read_text(encoding="utf-8")
    admin = int(
        re.search(r"leaflet-airAdmin-pane\s*\{\s*z-index:\s*(\d+)", css).group(1)
    )
    halo = int(re.search(r"leaflet-airHalo-pane\s*\{\s*z-index:\s*(\d+)", css).group(1))
    assert (
        admin < halo < 400
    )  # 400 = el panel de superposiciones (líneas y patrones) de Leaflet
