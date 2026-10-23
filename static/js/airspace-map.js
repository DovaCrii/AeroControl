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
  var PLANE =
    '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">' +
    '<path fill="currentColor" d="M12 2l2 7 8 4v2l-8-1.5V19l2.5 2v1L12 21l-4.5 1v-1L10 19v-5.5L2 15v-2l8-4z"/></svg>';

  var features = [];
  var byId = {};
  var groups = {};
  var map = null;
  var svgRenderer = null;
  var canvasRenderer = null;
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
  function planeIcon(kind) {
    return L.divIcon({
      className: "air-plane-wrap",
      html: '<span class="air-plane air-plane--' + kind + '">' + PLANE + "</span>",
      iconSize: [26, 26],
      iconAnchor: [13, 13],
    });
  }

  function airstripColor() {
    var value = getComputedStyle(document.documentElement).getPropertyValue("--ac-text-secondary");
    return value.trim() || "#555555";
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
      var dot = L.circleMarker([entry.lat, entry.lon], {
        renderer: canvasRenderer,
        radius: 3,
        weight: 1,
        color: airstripColor(),
        fillColor: airstripColor(),
        fillOpacity: 0.7,
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
    } else if (outline) {
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
      shape.on("click", function (event) {
        L.DomEvent.stopPropagation(event);
        featureClick(entry.id, event);
      });
      shape.bindTooltip(tipNode(titleOf(entry)), { sticky: true });
      layers.push(shape);
      if (zone) {
        layers.push(marker(entry, badgeIcon(kind), titleOf(entry)));
      }
    } else if (zone) {
      layers.push(marker(entry, badgeIcon(kind), titleOf(entry)));
    }
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
    features.forEach(function (entry) {
      var want = entry.passes && groupVisible(entry);
      if (want === entry.shown) {
        return;
      }
      entry.layers.forEach(function (layer) {
        try {
          if (want) {
            layer.addTo(map);
          } else {
            map.removeLayer(layer);
          }
        } catch (error) {
          reportError("layer " + entry.id, error);
        }
      });
      entry.shown = want;
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
    return distanceText(km) + (entry.geometry ? " (" + T.toCentre + ")" : "");
  }

  function renderRow(entry, withDistance) {
    var item = el("li", "air-result");
    var button = el("button", "air-row");
    button.type = "button";
    button.dataset.id = entry.id;
    button.appendChild(el("span", "air-row-kind air-row-kind--" + entry.kind, cfg.kinds[entry.kind]));
    var main = el("span", "air-row-main");
    main.appendChild(el("strong", "air-row-code", entry.code || ""));
    main.appendChild(el("span", "air-row-name", entry.name));
    if (entry.kind === "airstrip") {
      main.appendChild(el("span", "air-row-flag", "(" + T.unofficial + ")"));
    }
    button.appendChild(main);
    if (withDistance) {
      var d = describeDistance(entry);
      if (d) {
        button.appendChild(el("span", "air-row-dist", d));
      }
    }
    if (entry.id === selectedId) {
      button.setAttribute("aria-current", "true");
    }
    item.appendChild(button);
    return item;
  }

  var ROW_LIMIT = 150;

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
      total = rows.length;
    } else {
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
    $("air-fiche-unofficial").hidden = entry.kind !== "airstrip";
    setText("air-f-vertical", entry.vertical, T.notStated);
    setText("air-f-schedule", entry.schedule, T.notStated);
    setText("air-f-text", entry.text, T.notStated);
    setText("air-f-center", entry.dms);
    setText(
      "air-f-place",
      [entry.region, entry.commune].filter(Boolean).join(" · "),
      T.notStated
    );
    var ifis = $("air-f-ifis");
    if (entry.ifis) {
      $("air-f-ifis-link").href = entry.ifis;
      ifis.hidden = false;
    } else {
      ifis.hidden = true;
    }
  }

  function styleSelected(entry, on) {
    entry.layers.forEach(function (layer) {
      if (layer.setStyle && layer.eachLayer) {
        layer.setStyle({ weight: on ? 5 : 2 });
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
    var entry = byId[id];
    if (!entry) {
      return;
    }
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
    Array.prototype.forEach.call(resultsNode.querySelectorAll(".air-row"), function (row) {
      if (row.dataset.id === id) {
        row.setAttribute("aria-current", "true");
      } else {
        row.removeAttribute("aria-current");
      }
    });
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
      var button = el("button", "air-row");
      button.type = "button";
      button.dataset.id = item.id;
      button.appendChild(el("span", "air-row-kind air-row-kind--" + item.kind, cfg.kinds[item.kind]));
      var main = el("span", "air-row-main");
      main.appendChild(el("strong", "air-row-code", item.code || ""));
      main.appendChild(el("span", "air-row-name", item.name));
      button.appendChild(main);
      if (item.distance_km) {
        var text = distanceText(item.distance_km);
        if (withHeading && item.bearing_deg != null) {
          text += " · " + headingText(item.bearing_deg);
        }
        button.appendChild(el("span", "air-row-dist", text));
      }
      li.appendChild(button);
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
      span.innerHTML = PLANE; // SVG fijo de este archivo, sin datos de la fuente.
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
    host.appendChild(el("p", "air-legend-sep", T.layerOwnHeading));
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
      label.appendChild(el("span", "", ownName(own.key)));
      host.appendChild(label);
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
      label.appendChild(el("span", "", cfg.kinds[kind] + " (" + counts[kind] + ")"));
      host.appendChild(label);
    });
    buildOwnLegend(host);
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
      features.forEach(function (entry) {
        entry.layers.forEach(function (layer) {
          if (layer.options && layer.options.airstrip) {
            layer.setStyle({ color: color, fillColor: color });
          }
        });
      });
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
