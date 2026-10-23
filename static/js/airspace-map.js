/* LV-357 (fase 3): la pantalla «Espacio aéreo» de Entorno.

   Dibuja el JSON de `data.json` (la foto vigente del mapa ZONAS SENSIBLES) en Leaflet, con buscador,
   filtros, capas conmutables, medir, círculo de radio y «¿qué hay cerca de aquí?».

   Reglas que este archivo respeta:
   - NADA de lo que viene de la fuente entra como HTML: todo es `textContent`. No hay `innerHTML` con
     datos; los únicos `innerHTML` son SVG estáticos de este archivo.
   - Los límites verticales, el horario y la coordinación se muestran COMO los escribió la fuente: no se
     convierten ni se interpretan. No hay «puede volar», ni buffers, ni «activa ahora».
   - Las cuentas de geometría que deciden «esta zona toca su círculo» las hace el servidor (`near/`) con
     las mismas funciones de `apps/geo/airspace_geometry.py`; aquí sólo se miden segmentos para «medir».
   - Sin llamadas nuevas: `fetch` va al mismo origen y los fondos son los de `GEO_TILE_PROVIDERS`.
   - Un color nunca va solo: zona = color + patrón + letra; capa = casilla con texto.
   Leaflet se carga como script clásico antes que éste (`L` es global). */
(function () {
  "use strict";

  var configNode = document.getElementById("air-config");
  if (!configNode || !window.L || !window.AirspaceSearch) {
    return;
  }
  var cfg = JSON.parse(configNode.textContent);
  var T = cfg.i18n;
  var Search = window.AirspaceSearch;

  function $(id) {
    return document.getElementById(id);
  }
  function fmt(text, values) {
    return String(text).replace(/\{(\w+)\}/g, function (whole, key) {
      return values[key] != null ? values[key] : whole;
    });
  }
  /* El motivo de un fallo queda en la consola (nombre, estado y mensaje; nunca datos de la fuente). Antes
     un `catch` mostraba un mensaje genérico sin dejar rastro y un fallo de dibujo parecía un fallo de red. */
  function reportError(where, error) {
    if (window.console && console.error) {
      console.error("airspace-map: " + where + ": " + (error && error.message ? error.message : error));
    }
  }
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text != null) {
      node.textContent = text;
    }
    return node;
  }

  /* ── medidas (sólo para «medir»; el resto lo calcula el servidor) ───────── */
  var KM_PER_NM = 1.852;
  function rad(deg) {
    return (deg * Math.PI) / 180;
  }
  function haversineKm(lat1, lon1, lat2, lon2) {
    var dLat = rad(lat2 - lat1);
    var dLon = rad(lon2 - lon1);
    var a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 6371.0088 * 2 * Math.asin(Math.min(1, Math.sqrt(a)));
  }
  function bearingDeg(lat1, lon1, lat2, lon2) {
    var p1 = rad(lat1);
    var p2 = rad(lat2);
    var dl = rad(lon2 - lon1);
    var y = Math.sin(dl) * Math.cos(p2);
    var x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
    return (((Math.atan2(y, x) * 180) / Math.PI) + 360) % 360;
  }
  function distanceText(km) {
    var digits = km < 10 ? 2 : km < 100 ? 1 : 0;
    return km.toFixed(digits) + " " + T.km + " · " + (km / KM_PER_NM).toFixed(digits) + " " + T.nm;
  }
  function headingText(deg) {
    return String(Math.round(deg)).padStart(3, "0") + "° " + T.heading;
  }

  /* ── tipos: letra, grupo, orden ─────────────────────────────────────────── */
  var LETTERS = { prohibited: "P", restricted: "R", danger: "D", naval: "N" };
  var KIND_ORDER = [
    "airport",
    "aerodrome",
    "prohibited",
    "restricted",
    "danger",
    "naval",
    "fir_boundary",
    "airstrip",
  ];
  var AIRSTRIP_MIN_ZOOM = 8;
  var LABEL_MIN_ZOOM = 9;
  /* LV-367: los íconos viven en el sprite `air-i-*` de la plantilla; aquí sólo se nombran. */
  function iconMarkup(name) {
    return (
      '<svg class="air-ic" aria-hidden="true" focusable="false"><use href="#air-i-' + name + '"/></svg>'
    );
  }
  function iconNode(name) {
    var svg = svgNode("svg", { class: "air-ic", "aria-hidden": "true", focusable: "false" });
    var use = svgNode("use", {});
    use.setAttribute("href", "#air-i-" + name);
    svg.appendChild(use);
    return svg;
  }
  var KIND_ICONS = {
    airport: "airport",
    aerodrome: "aerodrome",
    prohibited: "prohibited",
    restricted: "restricted",
    danger: "danger",
    naval: "naval",
    fir_boundary: "fir_boundary",
    airstrip: "airstrip",
    commune: "commune",
    region: "region",
    undemarcated: "undemarcated",
  };
  /* LV-367 (fase 7): la capa «Límites administrativos». LOD 1 con zoom <= 7, LOD 2 con zoom >= 8; los
     nombres de región desde el zoom 5 y los de comuna desde el 9. Nada se pide mientras la capa está
     apagada: el padrón de búsqueda (nombres y encuadres, sin geometría) ya viene en la configuración. */
  var ADMIN_LOD_SPLIT_ZOOM = 7;
  var ADMIN_LABEL_ZOOM = { region: 5, commune: 9 };
  var ADMIN_KINDS = ["commune", "region", "undemarcated"];

  var features = [];
  var byId = {};
  var groups = {};
  var map = null;
  var svgRenderer = null;
  var haloRenderer = null;
  var adminRenderer = null;
  var canvasRenderer = null;
  var adminPool = [];
  var adminById = {};
  var admin = {
    on: false,
    lod: 0,
    data: {},
    loading: {},
    levels: {},
    labels: [],
    labelsBuilt: false,
    highlight: [],
    selected: null,
  };
  var selectedAdminId = null;
  var selectedId = null;
  var reference = cfg.reference || null;
  var tool = "";
  var markerLayer = null;
  var circleLayer = null;
  var measureLine = null;
  var measurePoints = [];

  var statusNode = $("air-status");
  var resultsNode = $("air-results");

  /* ── mapa ───────────────────────────────────────────────────────────────── */
  function svgNode(name, attrs) {
    var node = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.keys(attrs || {}).forEach(function (key) {
      node.setAttribute(key, attrs[key]);
    });
    return node;
  }

  /* Un patrón por tipo (además del color y la letra): cruzado = prohibida, diagonal = restringida,
     puntos = peligrosa, vertical = naval. Los colores salen de clases CSS con tokens `--sev-*`, así que
     siguen el tema claro/oscuro sin tocar este archivo. */
  function addPatterns(svg) {
    var defs = svgNode("defs");
    var shapes = {
      prohibited: [["path", { d: "M0 0L8 8M8 0L0 8" }]],
      restricted: [["path", { d: "M-1 7L7 -1M1 9L9 1" }]],
      danger: [["circle", { cx: 4, cy: 4, r: 1.4 }]],
      naval: [["path", { d: "M2 0V8M6 0V8" }]],
    };
    Object.keys(shapes).forEach(function (kind) {
      var pattern = svgNode("pattern", {
        id: "air-pat-" + kind,
        width: 8,
        height: 8,
        patternUnits: "userSpaceOnUse",
        class: "air-pat air-pat--" + kind,
      });
      pattern.appendChild(svgNode("rect", { width: 8, height: 8, class: "air-pat-bg" }));
      shapes[kind].forEach(function (shape) {
        pattern.appendChild(svgNode(shape[0], Object.assign({ class: "air-pat-mark" }, shape[1])));
      });
      defs.appendChild(pattern);
    });
    svg.insertBefore(defs, svg.firstChild);
  }

  function createMap() {
    map = L.map("air-map", { preferCanvas: true, zoomControl: true });
    canvasRenderer = L.canvas({ padding: 0.5 });
    svgRenderer = L.svg({ padding: 0.5 });
    // El halo oscuro de las zonas va en su propio panel, DEBAJO de todas las líneas (z-index en CSS).
    map.createPane("airHalo");
    haloRenderer = L.svg({ padding: 0.5, pane: "airHalo" });
    // Los límites administrativos van en lienzo (decenas de miles de vértices) y debajo de las zonas.
    map.createPane("airAdmin");
    adminRenderer = L.canvas({ padding: 0.5, pane: "airAdmin" });
    var bases = {};
    var providers = cfg.tileProviders || [];
    var initial = providers.find(function (p) { return p.default; }) || providers[0];
    providers.forEach(function (provider) {
      var layer = L.tileLayer(provider.url, {
        attribution: provider.attribution || "",
        maxZoom: provider.maxZoom || 19,
      });
      bases[provider.name] = layer;
      if (provider === initial) {
        layer.addTo(map);
      }
    });
    if (Object.keys(bases).length > 1) {
      L.control.layers(bases, {}, { position: "topright" }).addTo(map);
    }
    // Sin tamaño aún (contenedor oculto) se deja una vista fija: setView/fitBounds no terminarían.
    if (reference) {
      map.setView([reference.lat, reference.lon], 8, { animate: false });
    } else {
      if (canMove()) {
        map.fitBounds([[-56, -76], [-17, -66]], { animate: false });
      } else {
        map.setView([-35.5, -71], 4, { animate: false });
      }
    }
    map.addLayer(svgRenderer);
    if (svgRenderer._container) {
      addPatterns(svgRenderer._container);
    }
    map.on("click", function (event) {
      mapClick(event.latlng);
    });
    map.on("zoomend", syncAirstrips);
    map.on("zoomend", onAdminZoom);
    map.on("dblclick", function () {
      if (tool !== "measure") {
        return;
      }
      // Los dos clics del doble clic ya sumaron el mismo punto dos veces: se quita el repetido.
      if (measureLine && measurePoints.length > 1) {
        measurePoints.pop();
        measureLine.setLatLngs(measurePoints);
        renderMeasure();
      }
      setTool("");
    });
  }

  /* Mover la vista de un mapa sin tamaño (contenedor oculto, pestaña en segundo plano) no tiene sentido y
     en Leaflet puede no terminar: se omite hasta que el contenedor mida algo. */
  function canMove() {
    var size = map.getSize();
    return size.x > 0 && size.y > 0;
  }

  /* ── dibujo de cada elemento ─────────────────────────────────────────────── */
  function badgeIcon(kind) {
    return L.divIcon({
      className: "air-badge-wrap",
      html: '<span class="air-badge air-badge--' + kind + '">' + LETTERS[kind] + "</span>",
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    });
  }
  /* Jerarquía: aeropuerto = disco de 30 px con borde; aeródromo = 22 px (igual que la insignia de zona). */
  function planeIcon(kind) {
    var size = kind === "airport" ? 30 : 22;
    return L.divIcon({
      className: "air-plane-wrap",
      html: '<span class="air-plane air-plane--' + kind + '">' + iconMarkup("plane") + "</span>",
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
  }

  /* El código de la zona o del aeródromo, con halo, desde el zoom 9. Es un NODO (nunca un string): el
     texto viene de la fuente y Leaflet metería un string con `innerHTML`. */
  function codeLabel(entry, below) {
    var node = el("span", "air-tag", entry.code);
    var layer = L.marker([entry.lat, entry.lon], {
      icon: L.divIcon({
        className: "air-tag-wrap",
        html: node,
        iconSize: [80, 14],
        iconAnchor: [40, -below],
      }),
      interactive: false,
      keyboard: false,
    });
    layer.airMinZoom = LABEL_MIN_ZOOM;
    return layer;
  }

  function cssVar(name, fallback) {
    var value = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (value && value.trim()) || fallback;
  }
  function airstripColor() {
    return cssVar("--id-air-dot", "#e6edf6");
  }
  function haloColor() {
    return cssVar("--id-air-halo", "#0b1220");
  }

  function marker(entry, icon, title) {
    var m = L.marker([entry.lat, entry.lon], {
      icon: icon,
      title: title,
      alt: title,
      keyboard: true,
      riseOnHover: true,
    });
    m.on("click", function (event) {
      featureClick(entry.id, event);
    });
    return m;
  }

  function titleOf(entry) {
    var label = cfg.kinds[entry.kind] || entry.kind;
    return (entry.code ? entry.code + " · " : "") + entry.name + " (" + label + ")";
  }

  /* La forma que Leaflet puede dibujar, o null. Una `GeometryCollection` (zona + su punto de rótulo,
     como SC-P29) se aplana a sus líneas y polígonos: el punto ya tiene su insignia y, como GeoJSON, Leaflet
     lo dibujaría con el icono de imagen por defecto. Sin piezas o con coordenadas ausentes: null, y la
     zona se queda sólo con su insignia en vez de tumbar el mapa entero (LV-363). */
  function drawable(geometry) {
    if (!geometry || typeof geometry !== "object") {
      return null;
    }
    if (geometry.type === "GeometryCollection") {
      var parts = (geometry.geometries || []).map(drawable).filter(Boolean);
      parts = parts.filter(function (part) {
        return part.type !== "Point" && part.type !== "MultiPoint";
      });
      return parts.length ? { type: "GeometryCollection", geometries: parts } : null;
    }
    return Array.isArray(geometry.coordinates) && geometry.coordinates.length ? geometry : null;
  }
  function hasArea(geometry) {
    if (geometry.type === "GeometryCollection") {
      return geometry.geometries.some(hasArea);
    }
    return geometry.type === "Polygon" || geometry.type === "MultiPolygon";
  }

  function draw(entry) {
    var kind = entry.kind;
    var outline = entry.geometry ? drawable(entry.geometry) : null;
    var layers = [];
    var zone = LETTERS[kind] != null;
    if (kind === "airstrip") {
      // Radio 4 con halo oscuro debajo (un segundo círculo, no interactivo): se lee sobre claro y oscuro.
      var ring = L.circleMarker([entry.lat, entry.lon], {
        renderer: canvasRenderer,
        radius: 6.5,
        weight: 0,
        fillColor: haloColor(),
        fillOpacity: 0.9,
        interactive: false,
      });
      ring.options.airHalo = true;
      layers.push(ring);
      var dot = L.circleMarker([entry.lat, entry.lon], {
        renderer: canvasRenderer,
        radius: 4,
        weight: 0,
        fillColor: airstripColor(),
        fillOpacity: 1,
      });
      dot.on("click", function (event) {
        // Un círculo burbujea al mapa: sin esto, con una herramienta activa el clic contaba dos veces.
        L.DomEvent.stopPropagation(event);
        featureClick(entry.id, event);
      });
      dot.bindTooltip(tipNode(titleOf(entry)), { direction: "top" });
      dot.options.airstrip = true;
      layers.push(dot);
    } else if (kind === "airport" || kind === "aerodrome") {
      layers.push(marker(entry, planeIcon(kind), titleOf(entry)));
      if (entry.code) {
        layers.push(codeLabel(entry, kind === "airport" ? 17 : 13));
      }
    } else if (outline) {
      // Doble trazo: un halo oscuro de 4 px (debajo de todo, sin eventos) y la línea de color de 2 px.
      var halo = L.geoJSON(outline, {
        renderer: haloRenderer,
        style: function () {
          return { className: "air-halo", weight: 4, fill: false, interactive: false };
        },
      });
      halo.airRole = "halo";
      layers.push(halo);
      var shape = L.geoJSON(outline, {
        renderer: svgRenderer,
        style: function (geo) {
          // Leaflet envuelve la geometría en un Feature: el tipo está en `geo.geometry`.
          var closed = hasArea(geo.geometry || geo);
          var base = { className: "air-shape air-shape--" + kind, weight: 2, interactive: true };
          if (closed && zone) {
            base.fill = true;
            base.fillColor = "url(#air-pat-" + kind + ")";
            base.fillOpacity = 1;
          } else {
            base.fill = false;
          }
          return base;
        },
      });
      shape.airRole = "line";
      shape.on("click", function (event) {
        L.DomEvent.stopPropagation(event);
        featureClick(entry.id, event);
      });
      shape.bindTooltip(tipNode(titleOf(entry)), { sticky: true });
      layers.push(shape);
      if (zone) {
        layers.push(marker(entry, badgeIcon(kind), titleOf(entry)));
        if (entry.code) {
          layers.push(codeLabel(entry, 14));
        }
      }
    } else if (zone) {
      layers.push(marker(entry, badgeIcon(kind), titleOf(entry)));
      if (entry.code) {
        layers.push(codeLabel(entry, 14));
      }
    }
    layers.forEach(function (layer) {
      if (kind === "airstrip") {
        layer.airMinZoom = AIRSTRIP_MIN_ZOOM;
      }
    });
    entry.layers = layers;
    entry.shown = false;
  }

  function groupFor(kind) {
    if (!groups[kind]) {
      groups[kind] = { key: kind, layer: L.layerGroup(), on: true };
    }
    return groups[kind];
  }

  function groupVisible(entry) {
    var group = groups[entry.kind];
    if (!group || !group.on) {
      return false;
    }
    return entry.kind !== "airstrip" || map.getZoom() >= AIRSTRIP_MIN_ZOOM;
  }

  /* Pone o saca de su grupo lo que pasa (o no) los filtros, y el grupo de la capa. */
  function syncLayers() {
    var zoom = map.getZoom();
    features.forEach(function (entry) {
      var visible = !!(entry.passes && groupVisible(entry));
      entry.layers.forEach(function (layer) {
        // Cada pieza tiene su zoom mínimo (los rótulos desde 9, las pistas desde 8).
        var want = visible && zoom >= (layer.airMinZoom || 0);
        if (want === !!layer.airOn) {
          return;
        }
        try {
          if (want) {
            layer.addTo(map);
          } else {
            map.removeLayer(layer);
          }
        } catch (error) {
          reportError("layer " + entry.id, error);
        }
        layer.airOn = want;
      });
      entry.shown = visible;
    });
  }
  function syncAirstrips() {
    syncLayers();
  }

  /* ── filtros y resultados ────────────────────────────────────────────────── */
  function filters() {
    return {
      kind: $("air-kind").value,
      folder: $("air-folder").value,
      fir: $("air-fir").value,
      onlyCode: $("air-only-code").checked,
    };
  }

  function passes(entry, f) {
    return (
      (!f.kind || entry.kind === f.kind) &&
      (!f.folder || entry.folder === f.folder) &&
      (!f.fir || entry.fir === f.fir) &&
      (!f.onlyCode || !!entry.code)
    );
  }

  function kindRank(kind) {
    var i = KIND_ORDER.indexOf(kind);
    return i === -1 ? KIND_ORDER.length : i;
  }

  function sortBase(a, b) {
    return (
      kindRank(a.kind) - kindRank(b.kind) ||
      (a.code || "~").localeCompare(b.code || "~") ||
      a.name.localeCompare(b.name)
    );
  }

  function describeDistance(entry) {
    if (!reference) {
      return "";
    }
    var km = haversineKm(reference.lat, reference.lon, entry.lat, entry.lon);
    var heading = headingText(bearingDeg(reference.lat, reference.lon, entry.lat, entry.lon));
    return distanceText(km) + " · " + heading + (entry.geometry ? " (" + T.toCentre + ")" : "");
  }

  /* Una fila de resultados: ícono del tipo, código en monoespaciado, nombre, y debajo el tipo y la
     distancia con su rumbo. Todo con `textContent`: el nombre y el código vienen de la fuente. */
  function rowButton(entry, distance, unofficial) {
    var button = el("button", "air-row");
    button.type = "button";
    button.dataset.id = entry.id;
    var icon = el("span", "air-row-icon air-row-icon--" + entry.kind);
    icon.setAttribute("aria-hidden", "true");
    icon.appendChild(iconNode(KIND_ICONS[entry.kind] || "airstrip"));
    button.appendChild(icon);
    var main = el("span", "air-row-main");
    main.appendChild(el("strong", "air-row-code", entry.code || ""));
    main.appendChild(el("span", "air-row-name", entry.name));
    if (unofficial) {
      main.appendChild(el("span", "air-row-flag", "(" + T.unofficial + ")"));
    }
    button.appendChild(main);
    var meta = el("span", "air-row-meta");
    meta.appendChild(el("span", "air-row-kind air-row-kind--" + entry.kind, cfg.kinds[entry.kind]));
    if (distance) {
      meta.appendChild(el("span", "air-row-dist", distance));
    }
    button.appendChild(meta);
    return button;
  }

  function isAdminId(id) {
    return String(id).indexOf(Search.ADMIN_ID_PREFIX) === 0;
  }

  function renderRow(entry, withDistance) {
    var item = el("li", "air-result");
    var button = isAdminId(entry.id)
      ? rowButton(entry, entry.region || "", false)
      : rowButton(entry, withDistance ? describeDistance(entry) : "", entry.kind === "airstrip");
    if (entry.id === selectedId || entry.id === selectedAdminId) {
      button.setAttribute("aria-current", "true");
    }
    item.appendChild(button);
    return item;
  }

  var ROW_LIMIT = 150;

  /* Las comunas y regiones no tienen carpeta, FIR ni código de zona: los filtros que los suponen las
     excluyen, y el de tipo las deja o las saca. */
  function adminPoolFor(f) {
    if (f.folder || f.fir || f.onlyCode) {
      return [];
    }
    return adminPool.filter(function (entry) {
      return !f.kind || entry.kind === f.kind;
    });
  }

  function currentPool() {
    var f = filters();
    return features.filter(function (entry) {
      return passes(entry, f);
    });
  }

  function refresh() {
    var f = filters();
    features.forEach(function (entry) {
      entry.passes = passes(entry, f);
    });
    syncLayers();
    renderResults();
  }

  function setStatus(text) {
    statusNode.textContent = text;
  }

  function renderResults() {
    var query = $("air-q").value;
    var parsed = Search.parseQuery(query);
    var pool = currentPool();
    var rows = [];
    var withDistance = !!reference;
    var total = 0;
    resultsNode.textContent = "";
    if (parsed.type === "invalid_coordinate") {
      setStatus(fmt(T.invalidCoordinate, { reason: reasonText(parsed.reason) }));
      return;
    }
    if (parsed.type === "coordinate") {
      rows = pool.slice();
      if (reference) {
        rows.sort(function (a, b) {
          return (
            haversineKm(reference.lat, reference.lon, a.lat, a.lon) -
            haversineKm(reference.lat, reference.lon, b.lat, b.lon)
          );
        });
      }
      total = rows.length;
    } else if (parsed.type === "empty") {
      var f = filters();
      rows = pool
        .filter(function (entry) {
          return entry.kind !== "airstrip" || f.kind === "airstrip";
        })
        .sort(sortBase);
      // Las comunas y regiones sólo se listan si se pidieron por tipo: 361 filas taparían lo demás.
      if (ADMIN_KINDS.indexOf(f.kind) !== -1) {
        rows = adminPoolFor(f).sort(function (a, b) {
          return a.name.localeCompare(b.name);
        });
      }
      total = rows.length;
    } else {
      pool = pool.concat(adminPoolFor(filters()));
      var found = Search.searchFeatures(query, pool, pool.length);
      rows = found.results.map(function (r) {
        return r.entry;
      });
      total = found.total;
    }
    rows.slice(0, ROW_LIMIT).forEach(function (entry) {
      resultsNode.appendChild(renderRow(entry, withDistance));
    });
    if (!total) {
      setStatus(T.noResults);
    } else {
      setStatus(fmt(T.resultsCount, { n: total }));
    }
    if (total > ROW_LIMIT) {
      resultsNode.appendChild(el("li", "air-more", fmt(T.moreResults, { n: total - ROW_LIMIT })));
    }
  }

  function reasonText(reason) {
    return (
      {
        latitude_out_of_range: T.reasonLat,
        longitude_out_of_range: T.reasonLon,
        invalid_minutes_or_seconds: T.reasonMinutes,
        sign_and_hemisphere: T.reasonSign,
        same_axis_twice: T.reasonAxis,
      }[reason] || reason
    );
  }

  /* ── selección y ficha ───────────────────────────────────────────────────── */
  function setText(id, text, emptyText) {
    $(id).textContent = text || emptyText || "";
  }

  function showFiche(entry) {
    $("air-fiche-empty").hidden = true;
    $("air-fiche-body").hidden = false;
    setText("air-fiche-name", (entry.code ? entry.code + " · " : "") + entry.name);
    setText("air-fiche-meta", cfg.kinds[entry.kind] + (entry.folder ? " · " + entry.folder : ""));
    $("air-fiche-use").setAttribute("href", "#air-i-" + (KIND_ICONS[entry.kind] || "airstrip"));
    $("air-fiche-unofficial").hidden = entry.kind !== "airstrip";
    setText("air-f-vertical", entry.vertical, T.notStated);
    setText("air-f-schedule", entry.schedule, T.notStated);
    setText("air-f-text", entry.text, T.notStated);
    setText("air-f-center", entry.dms);
    [["air-f-region", entry.region], ["air-f-commune", entry.commune]].forEach(function (pair) {
      $(pair[0]).textContent = pair[1] || "";
      $(pair[0]).hidden = !pair[1];
    });
    var ifis = $("air-f-ifis");
    if (entry.ifis) {
      $("air-f-ifis-link").href = entry.ifis;
      ifis.hidden = false;
    } else {
      ifis.hidden = true;
    }
  }

  /* Selección: la línea sube a 3 px (el halo a 5) y la zona se rellena sólido al 12 % (regla CSS
     `.is-selected`, que gana al patrón); al soltar vuelve al patrón. */
  function styleSelected(entry, on) {
    entry.layers.forEach(function (layer) {
      if (layer.setStyle && layer.eachLayer) {
        var halo = layer.airRole === "halo";
        layer.setStyle({ weight: halo ? (on ? 5 : 4) : on ? 3 : 2 });
        if (!halo) {
          layer.eachLayer(function (part) {
            var node = part.getElement && part.getElement();
            if (node) {
              node.classList.toggle("is-selected", on);
            }
          });
        }
        if (on && layer.bringToFront) {
          layer.bringToFront();
        }
      } else if (layer.getElement) {
        var node = layer.getElement();
        if (node) {
          node.classList.toggle("is-selected", on);
        }
      }
    });
  }

  function select(id, options) {
    if (isAdminId(id)) {
      selectAdmin(id, options);
      return;
    }
    var entry = byId[id];
    if (!entry) {
      return;
    }
    selectedAdminId = null;
    if (selectedId && byId[selectedId]) {
      styleSelected(byId[selectedId], false);
    }
    selectedId = id;
    showFiche(entry);
    if (!entry.shown) {
      entry.passes = true;
      var group = groups[entry.kind];
      if (group && !group.on) {
        group.on = true;
        var box = document.querySelector('[data-group="' + entry.kind + '"]');
        if (box) {
          box.checked = true;
        }
      }
      syncLayers();
    }
    styleSelected(entry, true);
    if ((!options || options.fly !== false) && canMove()) {
      if (entry.bbox) {
        map.fitBounds(
          [[entry.bbox[1], entry.bbox[0]], [entry.bbox[3], entry.bbox[2]]],
          { maxZoom: 12, padding: [30, 30] }
        );
      } else {
        map.setView([entry.lat, entry.lon], Math.max(map.getZoom(), 11));
      }
    }
    markCurrentRow();
    setStatus(fmt(T.selected, { name: entry.name }));
  }

  function featureClick(id, event) {
    if (tool) {
      mapClick(event.latlng);
      return;
    }
    select(id, { fly: false });
  }

  /* ── herramientas ────────────────────────────────────────────────────────── */
  var HINTS = { measure: "measureHint", circle: "circleHint", near: "nearHint" };

  function setTool(name) {
    tool = tool === name ? "" : name;
    ["measure", "circle", "near"].forEach(function (key) {
      $("air-tool-" + key).setAttribute("aria-pressed", String(tool === key));
    });
    $("air-tool-hint").textContent = tool ? T[HINTS[tool]] : "";
    $("air-map").classList.toggle("air-map--tool", !!tool);
    // Medir termina con doble clic: sin esto el doble clic además acercaba el mapa.
    if (map) {
      map.doubleClickZoom[tool === "measure" ? "disable" : "enable"]();
    }
    if (tool !== "measure") {
      stopMeasure(false);
    }
  }

  function clearTools() {
    setTool("");
    stopMeasure(true);
    if (markerLayer) {
      map.removeLayer(markerLayer);
      markerLayer = null;
    }
    if (circleLayer) {
      map.removeLayer(circleLayer);
      circleLayer = null;
    }
    $("air-near-out").hidden = true;
    $("air-near-lists").textContent = "";
    $("air-copy").hidden = true;
    clearAdmin();
    markCurrentRow();
  }

  function stopMeasure(clear) {
    if (clear && measureLine) {
      map.removeLayer(measureLine);
      measureLine = null;
      measurePoints = [];
      $("air-measure").hidden = true;
    }
  }

  function mapClick(latlng) {
    if (tool === "measure") {
      measurePoints.push([latlng.lat, latlng.lng]);
      if (!measureLine) {
        measureLine = L.polyline(measurePoints, {
          renderer: svgRenderer,
          className: "air-measure-line",
          weight: 3,
        }).addTo(map);
      } else {
        measureLine.setLatLngs(measurePoints);
      }
      renderMeasure();
    } else if (tool === "circle") {
      var radius = radiusKm();
      if (radius) {
        placeCircle(latlng.lat, latlng.lng, radius);
        queryNear(latlng.lat, latlng.lng, radius);
      }
    } else if (tool === "near") {
      placeMarker(latlng.lat, latlng.lng);
      queryNear(latlng.lat, latlng.lng, 0);
    }
  }

  function renderMeasure() {
    var node = $("air-measure");
    var total = 0;
    var last = null;
    for (var i = 1; i < measurePoints.length; i += 1) {
      var a = measurePoints[i - 1];
      var b = measurePoints[i];
      var leg = haversineKm(a[0], a[1], b[0], b[1]);
      total += leg;
      last = { km: leg, deg: bearingDeg(a[0], a[1], b[0], b[1]) };
    }
    node.hidden = false;
    node.textContent = "";
    node.appendChild(el("strong", "", T.measureTotal + ": " + distanceText(total)));
    if (last) {
      node.appendChild(
        el("span", "", " · " + T.measureLeg + ": " + distanceText(last.km) + " · " + headingText(last.deg))
      );
    }
  }

  function radiusKm() {
    var value = parseFloat(String($("air-radius").value).replace(",", "."));
    return isFinite(value) && value > 0 && value <= 1000 ? value : 0;
  }
  function syncRadiusNm() {
    var km = radiusKm();
    $("air-radius-nm").textContent = km ? "= " + (km / KM_PER_NM).toFixed(2) + " " + T.nm : "";
  }

  function placeMarker(lat, lon) {
    if (markerLayer) {
      map.removeLayer(markerLayer);
    }
    markerLayer = L.circleMarker([lat, lon], {
      renderer: svgRenderer,
      className: "air-refpoint",
      radius: 7,
      weight: 3,
      fillOpacity: 0.25,
    }).addTo(map);
    reference = { lat: lat, lon: lon, label: "" };
  }

  function placeCircle(lat, lon, radius) {
    placeMarker(lat, lon);
    if (circleLayer) {
      map.removeLayer(circleLayer);
    }
    circleLayer = L.circle([lat, lon], {
      renderer: svgRenderer,
      className: "air-circle",
      radius: radius * 1000,
      weight: 2,
      fillOpacity: 0.08,
      interactive: false,
    }).addTo(map);
  }

  /* ── «¿qué hay cerca?»: el servidor, con las funciones de geometría ──────── */
  var nearRequest = 0;

  function queryNear(lat, lon, radius) {
    var ticket = (nearRequest += 1);
    var url = cfg.nearUrl + "?lat=" + lat.toFixed(6) + "&lon=" + lon.toFixed(6);
    if (radius) {
      url += "&radius_km=" + radius;
    }
    $("air-near-out").hidden = false;
    $("air-near-point").textContent = T.loading;
    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error(String(response.status));
        }
        return response.json();
      })
      .then(function (data) {
        if (ticket === nearRequest) {
          renderNear(data);
        }
      })
      .catch(function (error) {
        reportError("near query", error);
        if (ticket === nearRequest) {
          $("air-near-point").textContent = T.nearFailed;
        }
      });
    renderResults();
  }

  function nearSection(title, items, withHeading) {
    var section = el("section", "air-near-sec");
    section.appendChild(el("h3", "air-near-title", title));
    if (!items.length) {
      section.appendChild(el("p", "air-help", T.none));
      return section;
    }
    var list = el("ul", "air-near-list");
    items.forEach(function (item) {
      var li = el("li");
      var text = "";
      if (item.distance_km) {
        text = distanceText(item.distance_km);
        if (withHeading && item.bearing_deg != null) {
          text += " · " + headingText(item.bearing_deg);
        }
      }
      li.appendChild(rowButton(item, text, false));
      list.appendChild(li);
    });
    section.appendChild(list);
    return section;
  }

  function renderNear(data) {
    var point = data.point;
    $("air-near-point").textContent =
      point.lat_dms + " " + point.lon_dms + " (" + point.lat.toFixed(5) + ", " + point.lon.toFixed(5) + ")";
    var copy = $("air-copy");
    copy.dataset.copy = point.lat_dms + " " + point.lon_dms;
    copy.hidden = false;
    var host = $("air-near-lists");
    host.textContent = "";
    host.appendChild(nearSection(T.inside, data.containing, false));
    if (data.radius_km) {
      host.appendChild(nearSection(T.touching, data.touching, false));
    }
    host.appendChild(nearSection(T.nearby, data.near, false));
    host.appendChild(nearSection(T.nearestAerodromes, data.aerodromes, true));
  }

  /* ── límites administrativos (LV-367, fase 7) ────────────────────────────────
     Comunas (y regiones, que se realzan rellenando sus comunas) de `admin.json`, con su nivel de detalle
     según el zoom. Colores leídos de variables CSS y releídos al cambiar el tema. Todo texto con
     `textContent`. Referencial: la fuente (BCN) lo dice, y los números vienen del servidor. */
  function adminColors() {
    return {
      line: cssVar("--id-air-admin-line", "#ffffff"),
      halo: cssVar("--id-air-admin-halo", "#0b1220"),
      region: cssVar("--id-air-admin-region", "#ffd166"),
    };
  }

  function wantedLod() {
    return map.getZoom() <= ADMIN_LOD_SPLIT_ZOOM ? 1 : 2;
  }

  function loadAdminLevel(lod) {
    if (admin.data[lod]) {
      return Promise.resolve(admin.data[lod]);
    }
    if (admin.loading[lod]) {
      return admin.loading[lod];
    }
    var request = fetch(cfg.adminUrl + "?lod=" + lod, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("admin.json answered " + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        if (!data || !Array.isArray(data.communes)) {
          throw new Error("unexpected data shape");
        }
        admin.data[lod] = data;
        admin.loading[lod] = null;
        return data;
      })
      .catch(function (error) {
        admin.loading[lod] = null;
        throw error;
      });
    admin.loading[lod] = request;
    return request;
  }

  function ringLatLngs(commune) {
    return commune.rings.map(function (ring) {
      var points = ring.map(function (p) {
        return [p[1], p[0]];
      });
      points.push(points[0]);
      return points;
    });
  }

  function drawAdminLevel(lod) {
    var colors = adminColors();
    var rings = [];
    admin.data[lod].communes.forEach(function (commune) {
      ringLatLngs(commune).forEach(function (ring) {
        rings.push(ring);
      });
    });
    var base = { renderer: adminRenderer, interactive: false, fill: false, lineJoin: "round" };
    var halo = L.polyline(rings, Object.assign({ color: colors.halo, weight: 3, opacity: 0.8 }, base));
    var line = L.polyline(rings, Object.assign({ color: colors.line, weight: 1, opacity: 0.95 }, base));
    halo.airRole = "adminHalo";
    line.airRole = "adminLine";
    admin.levels[lod] = { halo: halo, line: line };
  }

  function removeAdminLevels() {
    Object.keys(admin.levels).forEach(function (lod) {
      map.removeLayer(admin.levels[lod].halo);
      map.removeLayer(admin.levels[lod].line);
    });
  }

  function showAdminLevel(lod) {
    if (!admin.levels[lod]) {
      drawAdminLevel(lod);
    }
    removeAdminLevels();
    admin.levels[lod].halo.addTo(map);
    admin.levels[lod].line.addTo(map);
    admin.lod = lod;
    if (admin.selected) {
      drawAdminHighlight(admin.selected);
    }
  }

  /* Los rótulos son nodos (nunca strings): el nombre viene de un archivo de datos. Se crean la primera vez
     que se enciende la capa, y se ponen o sacan con el zoom. */
  function buildAdminLabels() {
    admin.labelsBuilt = true;
    (cfg.adminIndex || []).forEach(function (item) {
      if (!ADMIN_LABEL_ZOOM[item.kind]) {
        return;
      }
      var node = el("span", "air-admin-tag air-admin-tag--" + item.kind, item.name);
      var marker = L.marker(
        [(item.bbox[1] + item.bbox[3]) / 2, (item.bbox[0] + item.bbox[2]) / 2],
        {
          icon: L.divIcon({
            className: "air-admin-tag-wrap",
            html: node,
            iconSize: [160, 16],
            iconAnchor: [80, 8],
          }),
          interactive: false,
          keyboard: false,
        }
      );
      marker.airMinZoom = ADMIN_LABEL_ZOOM[item.kind];
      admin.labels.push(marker);
    });
  }

  function syncAdminLabels() {
    if (admin.on && !admin.labelsBuilt) {
      buildAdminLabels();
    }
    var zoom = map.getZoom();
    admin.labels.forEach(function (label) {
      var want = admin.on && zoom >= label.airMinZoom;
      if (want === !!label.airOn) {
        return;
      }
      try {
        if (want) {
          label.addTo(map);
        } else {
          map.removeLayer(label);
        }
      } catch (error) {
        reportError("admin label", error);
      }
      label.airOn = want;
    });
  }

  function showAdmin() {
    var lod = wantedLod();
    return loadAdminLevel(lod).then(function () {
      if (admin.on) {
        showAdminLevel(lod);
        syncAdminLabels();
        $("air-tool-hint").textContent = fmt(T.layerShown, { name: T.layerAdmin });
      }
    });
  }

  /* Enciende o apaga la capa. Devuelve la promesa de la carga (para que una búsqueda espere al dibujo). */
  function setAdminLayer(on, box) {
    admin.on = on;
    var retry = $("air-admin-retry");
    retry.hidden = true;
    if (!on) {
      removeAdminLevels();
      syncAdminLabels();
      $("air-tool-hint").textContent = fmt(T.layerHidden, { name: T.layerAdmin });
      return Promise.resolve();
    }
    $("air-tool-hint").textContent = T.adminLoading;
    return showAdmin().catch(function (error) {
      reportError("admin layer", error);
      admin.on = false;
      if (box) {
        box.checked = false;
      }
      $("air-tool-hint").textContent = T.adminFailed;
      retry.hidden = false;
    });
  }

  function onAdminZoom() {
    if (!admin.on) {
      return;
    }
    syncAdminLabels();
    if (wantedLod() !== admin.lod) {
      showAdmin().catch(function (error) {
        reportError("admin level", error);
        $("air-tool-hint").textContent = T.adminFailed;
      });
    }
  }

  /* Realce al elegir una comuna: halo, línea de 3 px y relleno del 12 %. Una región no tiene polígono
     propio (no se disuelve sin una librería de geometría): se rellenan sus comunas, sin trazo interno. */
  function clearAdminHighlight() {
    admin.highlight.forEach(function (layer) {
      map.removeLayer(layer);
    });
    admin.highlight = [];
  }

  function drawAdminHighlight(entry) {
    clearAdminHighlight();
    var data = admin.data[admin.lod] || admin.data[1] || admin.data[2];
    if (!data) {
      return;
    }
    var codes = [entry.code.replace(/^admin:/, "")];
    var code = codes[0];
    if (entry.kind === "region") {
      var region = data.regions.filter(function (r) {
        return r.code === code;
      })[0];
      codes = region ? region.communes : [];
    }
    var colors = adminColors();
    var base = { renderer: adminRenderer, interactive: false, lineJoin: "round" };
    data.communes.forEach(function (commune) {
      if (codes.indexOf(commune.code) === -1) {
        return;
      }
      var rings = ringLatLngs(commune);
      var parts = [];
      if (entry.kind !== "region") {
        var halo = L.polygon(
          rings,
          Object.assign({ color: colors.halo, weight: 6, opacity: 0.9, fill: false }, base)
        );
        halo.airRole = "adminHighlightHalo";
        parts.push(halo);
      }
      var shape = L.polygon(
        rings,
        Object.assign(
          entry.kind === "region"
            ? { stroke: false, fillColor: colors.region, fillOpacity: 0.12 }
            : { color: colors.region, weight: 3, fillColor: colors.region, fillOpacity: 0.12 },
          base
        )
      );
      shape.airRole = "adminHighlight";
      parts.push(shape);
      parts.forEach(function (layer) {
        layer.addTo(map);
        admin.highlight.push(layer);
      });
    });
  }

  function restyleAdmin() {
    var colors = adminColors();
    Object.keys(admin.levels).forEach(function (lod) {
      admin.levels[lod].halo.setStyle({ color: colors.halo });
      admin.levels[lod].line.setStyle({ color: colors.line });
    });
    admin.highlight.forEach(function (layer) {
      if (layer.airRole === "adminHighlightHalo") {
        layer.setStyle({ color: colors.halo });
      } else if (admin.selected && admin.selected.kind === "region") {
        layer.setStyle({ fillColor: colors.region });
      } else {
        layer.setStyle({ color: colors.region, fillColor: colors.region });
      }
    });
  }

  function adminSection(title, items) {
    var section = el("section", "air-near-sec");
    section.appendChild(el("h3", "air-near-title", title + " (" + items.length + ")"));
    if (!items.length) {
      section.appendChild(el("p", "air-help", T.none));
      return section;
    }
    var list = el("ul", "air-near-list");
    items.forEach(function (item) {
      var li = el("li");
      li.appendChild(rowButton(item, "", false));
      list.appendChild(li);
    });
    section.appendChild(list);
    return section;
  }

  function renderAdminContains(entry, data) {
    var contained = data.zones.filter(function (z) {
      return z.relation === "contained";
    });
    var touching = data.zones.filter(function (z) {
      return z.relation !== "contained";
    });
    var host = $("air-admin-lists");
    host.textContent = "";
    host.appendChild(adminSection(T.adminContained, contained));
    host.appendChild(adminSection(T.adminTouching, touching));
    host.appendChild(adminSection(T.adminAerodromes, data.aerodromes));
    var note = T.adminReferential;
    if (data.area.kind === "region") {
      note += " " + fmt(T.adminCommunes, { n: data.area.communes });
    }
    $("air-admin-note").textContent = note;
    $("air-admin-status").textContent = fmt(T.adminSummary, {
      zones: data.zones.length,
      aerodromes: data.aerodromes.length,
      name: entry.name,
    });
  }

  var adminTicket = 0;

  function loadAdminContains(entry) {
    var ticket = (adminTicket += 1);
    var code = entry.id.replace(/^admin:/, "");
    $("air-admin-contains-retry").hidden = true;
    $("air-admin-status").textContent = T.loading;
    $("air-admin-lists").textContent = "";
    fetch(cfg.adminContainsUrl.replace("__code__", encodeURIComponent(code)), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("admin contains answered " + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        if (ticket === adminTicket) {
          renderAdminContains(entry, data);
        }
      })
      .catch(function (error) {
        reportError("admin contains", error);
        if (ticket === adminTicket) {
          $("air-admin-status").textContent = T.nearFailed;
          $("air-admin-contains-retry").hidden = false;
        }
      });
  }

  function clearAdmin() {
    adminTicket += 1;
    admin.selected = null;
    selectedAdminId = null;
    clearAdminHighlight();
    $("air-admin-out").hidden = true;
    $("air-admin-lists").textContent = "";
  }

  function selectAdmin(id, options) {
    var entry = adminById[id];
    if (!entry) {
      return;
    }
    if (selectedId && byId[selectedId]) {
      styleSelected(byId[selectedId], false);
    }
    selectedId = null;
    $("air-fiche-empty").hidden = false;
    $("air-fiche-body").hidden = true;
    selectedAdminId = id;
    admin.selected = { code: id, kind: entry.kind, name: entry.name };
    $("air-admin-out").hidden = false;
    $("air-admin-name").textContent = entry.name;
    $("air-admin-note").textContent = T.adminReferential;
    if ((!options || options.fly !== false) && canMove()) {
      map.fitBounds(
        [[entry.bbox[1], entry.bbox[0]], [entry.bbox[3], entry.bbox[2]]],
        { padding: [30, 30] }
      );
    }
    // El realce necesita la geometría: elegir una comuna enciende la capa (y la pide por primera vez).
    var box = document.querySelector("[data-admin]");
    if (box) {
      box.checked = true;
    }
    if (admin.on) {
      drawAdminHighlight(admin.selected);
    } else {
      // Al terminar de cargar, `showAdminLevel` dibuja el realce de lo elegido.
      setAdminLayer(true, box);
    }
    loadAdminContains(entry);
    markCurrentRow();
    setStatus(fmt(T.selected, { name: entry.name }));
  }

  function markCurrentRow() {
    var current = selectedAdminId || selectedId;
    Array.prototype.forEach.call(resultsNode.querySelectorAll(".air-row"), function (row) {
      if (row.dataset.id === current) {
        row.setAttribute("aria-current", "true");
      } else {
        row.removeAttribute("aria-current");
      }
    });
  }

  /* ── coordenada escrita en el buscador ───────────────────────────────────── */
  function onCoordinate(parsed) {
    placeMarker(parsed.lat, parsed.lon);
    reference.label = parsed.lat.toFixed(5) + ", " + parsed.lon.toFixed(5);
    if (canMove()) {
      map.setView([parsed.lat, parsed.lon], Math.max(map.getZoom(), 11));
    }
    setReferenceNote();
    queryNear(parsed.lat, parsed.lon, 0);
  }

  function setReferenceNote() {
    var note = $("air-ref");
    if (reference && reference.label) {
      note.textContent = fmt(T.referenceFrom, { label: reference.label });
      note.hidden = false;
    } else {
      note.hidden = true;
    }
  }

  /* ── leyenda, filtros y arranque ─────────────────────────────────────────── */
  function swatchFor(kind) {
    var span = el("span", "air-swatch air-swatch--" + kind);
    span.setAttribute("aria-hidden", "true");
    if (LETTERS[kind]) {
      span.textContent = LETTERS[kind];
    } else if (kind === "airport" || kind === "aerodrome") {
      span.appendChild(iconNode("plane"));
    }
    return span;
  }

  /* ── capas propias (LV-358, E3): «Mis faenas» y «Permisos vigentes» ───────────
     Cada una existe sólo si el servidor la ofreció (`cfg.ownLayers`: la persona tiene su `view_*`), arranca
     APAGADA y se pide a `own-layers.json` recién al encenderla. Lo que llega es dato: los textos entran con
     `textContent` y los rótulos de Leaflet se pasan como NODOS (un string iría a `innerHTML`). */
  var ownGroups = {};

  function ownName(key) {
    return key === "sites" ? T.layerSites : T.layerPermits;
  }
  function tipNode(text) {
    return el("span", "", text);
  }
  function dateText(iso) {
    var parts = String(iso).split("-");
    return parts.length === 3 ? parts[2] + "-" + parts[1] + "-" + parts[0] : String(iso);
  }
  function drawSite(item) {
    var title = T.siteWord + " " + item.code + (item.name ? " · " + item.name : "");
    var icon = L.divIcon({
      className: "air-own-wrap",
      html: '<span class="air-own" aria-hidden="true">■</span>',
      iconSize: [18, 18],
      iconAnchor: [9, 9],
    });
    var m = L.marker([item.lat, item.lon], { icon: icon, title: title, alt: title, keyboard: true });
    m.bindTooltip(tipNode(title), { direction: "top" });
    return [m];
  }
  function drawPermit(item) {
    var title =
      T.permitWord + " " + (item.number || item.site) + " · " + item.site + " · " +
      fmt(T.validUntil, { date: dateText(item.valid_until) });
    var shapes = [];
    if (item.radius_km) {
      var circle = L.circle([item.lat, item.lon], {
        renderer: svgRenderer,
        radius: item.radius_km * 1000,
        className: "air-own-permit",
        interactive: true,
      });
      circle.bindTooltip(tipNode(title), { sticky: true });
      shapes.push(circle);
    }
    var dot = L.circleMarker([item.lat, item.lon], {
      renderer: svgRenderer,
      radius: 6,
      className: "air-own-permit-dot",
      interactive: true,
    });
    dot.bindTooltip(tipNode(title), { direction: "top" });
    shapes.push(dot);
    return shapes;
  }

  function setOwnLayer(key, on, box) {
    var group = ownGroups[key];
    group.on = on;
    if (!on) {
      group.layers.forEach(function (layer) {
        map.removeLayer(layer);
      });
      $("air-tool-hint").textContent = fmt(T.layerHidden, { name: ownName(key) });
      return;
    }
    var show = function () {
      if (!group.on) {
        return;
      }
      group.layers.forEach(function (layer) {
        layer.addTo(map);
      });
      $("air-tool-hint").textContent = group.layers.length
        ? fmt(T.layerShown, { name: ownName(key) })
        : T.layerOwnEmpty;
    };
    if (group.loaded) {
      show();
      return;
    }
    fetch(group.url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error(String(response.status));
        }
        return response.json();
      })
      .then(function (data) {
        data.items.forEach(function (item) {
          var drawn = key === "sites" ? drawSite(item) : drawPermit(item);
          drawn.forEach(function (layer) {
            group.layers.push(layer);
          });
        });
        group.loaded = true;
        show();
      })
      .catch(function (error) {
        reportError("own layer " + key, error);
        group.on = false;
        box.checked = false;
        $("air-tool-hint").textContent = T.layerOwnFailed;
      });
  }

  function buildOwnLegend(host) {
    var offered = cfg.ownLayers || [];
    if (!offered.length) {
      return;
    }
    $("air-legend-own-group").hidden = false;
    offered.forEach(function (own) {
      ownGroups[own.key] = { url: own.url, layers: [], loaded: false, on: false };
      var label = el("label", "air-legend-item");
      var box = el("input");
      box.type = "checkbox";
      box.checked = false;
      box.dataset.own = own.key;
      box.addEventListener("change", function () {
        setOwnLayer(own.key, box.checked, box);
      });
      var swatch = el("span", "air-swatch air-swatch--own-" + own.key, own.key === "sites" ? "■" : "◎");
      swatch.setAttribute("aria-hidden", "true");
      label.appendChild(box);
      label.appendChild(swatch);
      label.appendChild(el("span", "air-legend-name", ownName(own.key)));
      host.appendChild(label);
    });
  }

  /* «Límites administrativos»: APAGADA al abrir; no se pide nada hasta encenderla. El número es el de
     comunas (el repositorio no tiene localidades: se ofrecen comunas y la pantalla lo dice). */
  function buildAdminLegend(host) {
    var communes = (cfg.adminIndex || []).filter(function (item) {
      return item.kind === "commune";
    }).length;
    var label = el("label", "air-legend-item");
    var box = el("input");
    box.type = "checkbox";
    box.checked = false;
    box.dataset.admin = "1";
    box.addEventListener("change", function () {
      setAdminLayer(box.checked, box);
    });
    var swatch = el("span", "air-swatch air-swatch--admin");
    swatch.setAttribute("aria-hidden", "true");
    swatch.appendChild(iconNode("boundary"));
    label.appendChild(box);
    label.appendChild(swatch);
    label.appendChild(el("span", "air-legend-name", T.layerAdmin));
    label.appendChild(el("span", "air-count-pill", String(communes)));
    host.appendChild(label);
    $("air-admin-retry").addEventListener("click", function () {
      box.checked = true;
      setAdminLayer(true, box);
    });
  }

  function buildLegend(counts) {
    var host = $("air-legend-items");
    KIND_ORDER.forEach(function (kind) {
      if (!counts[kind]) {
        return;
      }
      var label = el("label", "air-legend-item");
      var box = el("input");
      box.type = "checkbox";
      box.checked = true;
      box.dataset.group = kind;
      box.addEventListener("change", function () {
        groupFor(kind).on = box.checked;
        syncLayers();
        $("air-tool-hint").textContent = fmt(box.checked ? T.layerShown : T.layerHidden, {
          name: cfg.kinds[kind],
        });
      });
      label.appendChild(box);
      label.appendChild(swatchFor(kind));
      label.appendChild(el("span", "air-legend-name", cfg.kinds[kind]));
      label.appendChild(el("span", "air-count-pill", String(counts[kind])));
      host.appendChild(label);
    });
    buildAdminLegend($("air-legend-admin"));
    buildOwnLegend($("air-legend-own"));
    // En un teléfono la leyenda arranca plegada: el mapa va primero.
    if (window.matchMedia && window.matchMedia("(max-width: 575.98px)").matches) {
      $("air-legend").removeAttribute("open");
    }
  }

  function fillSelect(id, values) {
    var select = $(id);
    values.forEach(function (value) {
      var option = el("option", "", value);
      option.value = value;
      select.appendChild(option);
    });
  }

  function unique(field) {
    var seen = {};
    features.forEach(function (entry) {
      if (entry[field]) {
        seen[entry[field]] = true;
      }
    });
    return Object.keys(seen).sort(function (a, b) {
      return a.localeCompare(b);
    });
  }

  function start(data) {
    features = data.features;
    var counts = {};
    features.forEach(function (entry) {
      byId[entry.id] = entry;
      counts[entry.kind] = (counts[entry.kind] || 0) + 1;
      entry.places = Search.normalizeText([entry.region, entry.commune].join(" "));
      entry.passes = true;
    });
    createMap();
    features.forEach(function (entry) {
      groupFor(entry.kind);
      try {
        draw(entry);
      } catch (error) {
        // Un elemento con forma imposible no puede tumbar los otros 500: queda en la lista, sin dibujo.
        reportError("draw " + entry.id, error);
        entry.layers = [];
        entry.shown = false;
      }
    });
    adminPool = Search.adminEntries(cfg.adminIndex || []);
    adminPool.forEach(function (entry) {
      adminById[entry.id] = entry;
    });
    // Los tipos de la búsqueda administrativa (sin «Zona sin demarcar»: se encuentra por su nombre).
    ["commune", "region"].forEach(function (kind) {
      var option = el("option", "", cfg.kinds[kind]);
      option.value = kind;
      $("air-kind").appendChild(option);
    });
    fillSelect("air-folder", unique("folder"));
    fillSelect("air-fir", unique("fir"));
    buildLegend(counts);
    setReferenceNote();
    syncLayers();
    renderResults();
    var preset = new URLSearchParams(window.location.search).get("q");
    if (preset) {
      $("air-q").value = preset;
      onQuery();
    }
  }

  function onQuery() {
    var parsed = Search.parseQuery($("air-q").value);
    if (parsed.type === "coordinate") {
      onCoordinate(parsed);
    }
    renderResults();
  }

  function bind() {
    var timer = null;
    $("air-q").addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(onQuery, 150);
    });
    $("air-q").addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        var first = resultsNode.querySelector(".air-row");
        if (first && Search.parseQuery($("air-q").value).type !== "coordinate") {
          select(first.dataset.id);
        }
      }
    });
    ["air-kind", "air-folder", "air-fir", "air-only-code"].forEach(function (id) {
      $(id).addEventListener("change", refresh);
    });
    ["measure", "circle", "near"].forEach(function (key) {
      $("air-tool-" + key).addEventListener("click", function () {
        setTool(key);
      });
    });
    $("air-tool-clear").addEventListener("click", clearTools);
    $("air-admin-contains-retry").addEventListener("click", function () {
      var entry = selectedAdminId && adminById[selectedAdminId];
      if (entry) {
        loadAdminContains(entry);
      }
    });
    $("air-radius").addEventListener("input", syncRadiusNm);
    syncRadiusNm();
    // Delegación: las filas de resultados y de «cerca» se rehacen a cada consulta.
    document.addEventListener("click", function (event) {
      var row = event.target.closest && event.target.closest(".air-row");
      if (row && row.dataset.id) {
        select(row.dataset.id);
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && tool) {
        setTool("");
      }
    });
    new MutationObserver(function () {
      var color = airstripColor();
      var halo = haloColor();
      features.forEach(function (entry) {
        entry.layers.forEach(function (layer) {
          if (layer.options && layer.options.airstrip) {
            layer.setStyle({ fillColor: color });
          } else if (layer.options && layer.options.airHalo) {
            layer.setStyle({ fillColor: halo });
          }
        });
      });
      if (map) {
        restyleAdmin();
      }
    }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }

  /* Carga con estado de error claro: el motivo va a la consola y la persona tiene «Reintentar». Si el
     fallo fue de red o de respuesta se vuelve a pedir; si el mapa ya se había creado (falló el arranque)
     no se puede rehacer sobre el mismo contenedor, así que se recarga la página. */
  var retryNode = $("air-retry");
  var mapCreated = false;

  function startOnce(data) {
    if (!data || !Array.isArray(data.features)) {
      throw new Error("unexpected data shape");
    }
    mapCreated = true;
    start(data);
  }

  function showLoadFailure(stage, error) {
    reportError(stage, error);
    setStatus(T.loadFailed);
    if (retryNode) {
      retryNode.hidden = false;
      retryNode.focus();
    }
  }

  function load() {
    if (retryNode) {
      retryNode.hidden = true;
    }
    setStatus(T.loading);
    fetch(cfg.dataUrl, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("data.json answered " + response.status);
        }
        return response.json();
      })
      .then(startOnce, function (error) {
        showLoadFailure("loading the data", error);
      })
      .catch(function (error) {
        showLoadFailure("starting the map", error);
      });
  }

  bind();
  if (retryNode) {
    retryNode.addEventListener("click", function () {
      if (mapCreated) {
        window.location.reload();
      } else {
        load();
      }
    });
  }
  load();
})();
