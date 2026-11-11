/* LV-427: mapa de la trayectoria de un log de vuelo (Leaflet vendorizado, sin librerías nuevas).
   Los datos llegan por `json_script` (#fa-map-data), nunca interpolados en el HTML. La polilínea se
   colorea por altura sobre el punto de despegue; despegue, aterrizaje y eventos warning/critical
   llevan marcador. Los textos del log van siempre como nodos DOM (`textContent`), nunca como HTML. */
(function () {
  "use strict";

  var PREFIX = "flight-analysis: ";
  var HALO = "#0b1220";

  function report(where, error) {
    if (window.console && window.console.error) {
      window.console.error(PREFIX + where + ": " + (error && error.message ? error.message : error));
    }
  }

  function fail(container, error, where) {
    report(where, error);
    var note = container.parentNode.querySelector(".mini-map-fallback");
    if (note) { note.hidden = false; }
    container.hidden = true;
  }

  /* Azul (bajo) -> verde -> rojo (alto). */
  function colour(ratio) {
    var hue = 220 - Math.max(0, Math.min(1, ratio)) * 220;
    return "hsl(" + Math.round(hue) + ", 85%, 48%)";
  }

  function text(content) {
    var node = document.createElement("span");
    node.textContent = content;
    return node;
  }

  /* Todas las capas base configuradas (GEO_TILE_PROVIDERS), con selector; la marcada por defecto
     (satélite) arranca visible. */
  function addTiles(L, map, tiles) {
    var list = tiles || [];
    var chosen = list.find(function (t) { return t.default; }) || list[0];
    var bases = {};
    var shown = null;
    list.forEach(function (t) {
      var layer = L.tileLayer(t.url, { attribution: t.attribution || "", maxZoom: t.maxZoom || 19 });
      bases[t.name || t.id] = layer;
      if (t === chosen) { layer.addTo(map); shown = layer; }
    });
    if (list.length > 1) { L.control.layers(bases, null, { position: "topright" }).addTo(map); }
    return shown;
  }

  /* Regreso automático: línea discontinua clara sobre el tramo, con halo oscuro. */
  function drawReturn(L, map, path) {
    if (!path || path.length < 2) { return false; }
    L.polyline(path, { color: HALO, weight: 7, opacity: 0.9 }).addTo(map);
    L.polyline(path, { color: "#ffffff", weight: 3, opacity: 1, dashArray: "8 8" }).addTo(map);
    return true;
  }

  function drawTrack(L, map, points) {
    var heights = points.map(function (p) { return p[2]; }).filter(function (h) { return h !== null; });
    var lo = heights.length ? Math.min.apply(null, heights) : 0;
    var hi = heights.length ? Math.max.apply(null, heights) : 0;
    var span = hi - lo;
    var group = L.featureGroup().addTo(map);
    L.polyline(points.map(function (p) { return [p[0], p[1]]; }),
      { color: HALO, weight: 6, opacity: 0.85 }).addTo(group);
    for (var i = 1; i < points.length; i += 1) {
      var h = points[i][2];
      var ratio = h === null || !span ? 0 : (h - lo) / span;
      L.polyline([[points[i - 1][0], points[i - 1][1]], [points[i][0], points[i][1]]],
        { color: h === null ? "#9ca3af" : colour(ratio), weight: 3.5, opacity: 1 }).addTo(group);
    }
    return { group: group, lo: lo, hi: hi, hasHeight: heights.length > 0 };
  }

  function mark(L, group, latlon, fill, label) {
    var marker = L.circleMarker(latlon, { radius: 7, color: HALO, weight: 2, fillColor: fill, fillOpacity: 1 });
    marker.bindTooltip(text(label), { direction: "top" });
    marker.addTo(group);
  }

  function legend(L, map, info, i18n, hasReturn) {
    var control = L.control({ position: "bottomright" });
    control.onAdd = function () {
      var box = L.DomUtil.create("div", "fa-legend");
      var title = document.createElement("div");
      title.className = "fa-legend-title";
      title.textContent = info.hasHeight ? i18n.height : i18n.noHeight;
      box.appendChild(title);
      if (info.hasHeight) {
        var bar = document.createElement("div");
        bar.className = "fa-legend-bar";
        bar.style.background = "linear-gradient(to right," + colour(0) + "," + colour(0.5) + "," + colour(1) + ")";
        box.appendChild(bar);
        var ends = document.createElement("div");
        ends.className = "fa-legend-ends";
        ends.appendChild(text(info.lo.toFixed(0)));
        ends.appendChild(text(info.hi.toFixed(0)));
        box.appendChild(ends);
      }
      if (hasReturn) {
        var row = document.createElement("div");
        row.className = "fa-legend-return";
        var sample = document.createElement("span");
        sample.className = "fa-legend-dash";
        sample.setAttribute("aria-hidden", "true");
        row.appendChild(sample);
        row.appendChild(text(" " + i18n.returnLeg));
        box.appendChild(row);
      }
      return box;
    };
    control.addTo(map);
  }

  function init() {
    var container = document.getElementById("fa-map");
    var node = document.getElementById("fa-map-data");
    if (!container || !node) { return; }
    try {
      var data = JSON.parse(node.textContent);
      var L = window.L;
      var map = L.map(container, { zoomControl: true });
      var base = addTiles(L, map, data.tiles);
      L.control.scale({ metric: true, imperial: false }).addTo(map);
      var track = drawTrack(L, map, data.points);
      var hasReturn = drawReturn(L, map, data.returnPath);
      var markers = L.featureGroup().addTo(map);
      if (data.sameSpot && data.takeoff) {
        mark(L, markers, data.takeoff, "#22c55e", data.i18n.takeoffLanding);
      } else {
        if (data.takeoff) { mark(L, markers, data.takeoff, "#22c55e", data.i18n.takeoff); }
        if (data.landing) { mark(L, markers, data.landing, "#111827", data.i18n.landing); }
      }
      (data.events || []).forEach(function (event) {
        var color = event.level === "critical" ? "#dc2626" : "#f59e0b";
        var label = (event.level === "critical" ? data.i18n.critical : data.i18n.warning) +
          " " + event.when + ": " + event.text;
        mark(L, markers, [event.lat, event.lon], color, label);
      });
      legend(L, map, track, data.i18n, hasReturn);
      map.fitBounds(track.group.getBounds(), { padding: [24, 24] });
      /* LV-430: el reporte imprimible reencuadra y espera las teselas antes de imprimir. */
      container._fa = { map: map, bounds: track.group.getBounds(), base: base };
    } catch (error) {
      fail(container, error, "init");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
