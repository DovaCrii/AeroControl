/* LV-368 (fase 4): mini-mapa de SOLO LECTURA de un plan geoespacial.
   Dibuja el centro, el círculo o los vértices del área (corredor, triangular, cuadricular) y el
   aeródromo más cercano con Leaflet vendorizado, sin geoman: no se edita nada acá. Los datos llegan por
   `json_script` (nunca interpolados en el HTML) y las teselas son las de `GEO_TILE_PROVIDERS`.

   Dos cuidados que salen de errores ya pagados en el mapa de espacio aéreo (LV-363):
   - Un contenedor oculto mide 0 y Leaflet puede no terminar al moverle la vista: si el mapa está dentro
     de un `<details>` cerrado se dibuja al abrirlo, y `canMove()` guarda cada `fitBounds`/`setView`.
   - Un `catch` mudo convierte un fallo de dibujo en «no pasó nada»: cada error se nombra en la consola
     como `mini-map: <dónde>: <mensaje>`, sin datos del plan. */
(function () {
  "use strict";

  var PREFIX = "mini-map: ";
  var DESKTOP = "(min-width: 768px)";
  /* Colores de trazo. El halo oscuro bajo el trazo claro mantiene el contorno legible sobre el satélite
     y sobre el callejero, que es lo que las teselas no garantizan. */
  var COLORS = { halo: "#0b1220", area: "#ffd166", amc: "#7dd3fc", center: "#ffffff" };

  function report(where, error) {
    if (window.console && window.console.error) {
      window.console.error(PREFIX + where + ": " + (error && error.message ? error.message : error));
    }
  }

  function readConfig(container) {
    var node = document.getElementById(container.dataset.miniMapConfig || "");
    if (!node) {
      throw new Error("no data element");
    }
    var config = JSON.parse(node.textContent);
    if (!config || !Array.isArray(config.areas)) {
      throw new Error("unexpected data shape");
    }
    return config;
  }

  /* «Visible» es que el contenedor mida algo **y** que su `<details>` esté abierto. Lo segundo no es
     redundante: Chromium conserva las medidas del contenido de un `<details>` cerrado
     (`content-visibility: hidden`), así que sólo mirar el tamaño dibujaba el mapa a ciegas, con las
     teselas sin pedir y sin la vista bien encuadrada. Se comprobó en el navegador integrado. */
  function isVisible(container) {
    var details = container.closest ? container.closest("details") : null;
    if (details && !details.open) {
      return false;
    }
    return container.clientWidth > 0 && container.clientHeight > 0;
  }

  function fail(container, error, where) {
    report(where, error);
    var details = container.closest ? container.closest("details") : null;
    var scope = details || container.parentNode;
    var note = scope && scope.querySelector ? scope.querySelector(".mini-map-fallback") : null;
    if (note) {
      note.hidden = false;
    }
    container.hidden = true;
  }

  function addTiles(L, map, tiles) {
    var list = tiles || [];
    var chosen = list.find(function (tile) { return tile.default; }) || list[0];
    if (!chosen) {
      return;
    }
    L.tileLayer(chosen.url, {
      attribution: chosen.attribution || "",
      maxZoom: chosen.maxZoom || 19
    }).addTo(map);
  }

  /* Cada geometría se dibuja aparte y con su propio `try`: una sola mal formada no tumba el mapa. */
  function drawGeometry(L, group, geometry, area) {
    try {
      if (geometry.type === "Point") {
        L.circleMarker([geometry.coordinates[1], geometry.coordinates[0]], {
          radius: 5, color: COLORS.halo, weight: 2, fillColor: COLORS.center, fillOpacity: 1
        }).addTo(group);
        return;
      }
      L.geoJSON(geometry, { style: { color: COLORS.halo, weight: 5, opacity: 0.9, fill: false } }).addTo(group);
      L.geoJSON(geometry, {
        style: { color: COLORS.area, weight: 2.5, opacity: 1, fillColor: COLORS.area, fillOpacity: 0.14 }
      }).addTo(group);
    } catch (error) {
      report("draw " + (area && area.modality ? area.modality : "area"), error);
    }
  }

  function drawArea(L, group, area, i18n) {
    var polygons = 0;
    (area.geometries || []).forEach(function (geometry) {
      if (geometry.type !== "Point") {
        polygons += 1;
      }
      drawGeometry(L, group, geometry, area);
    });
    try {
      var center = area.center;
      /* El círculo se calcula cuando no hay uno dibujado, o cuando el área no es un círculo y el que se
         declara es el que la encierra (en trazo discontinuo: no es lo que se dibujó). */
      if (area.radius_m && (!polygons || area.enclosing)) {
        L.circle(center, {
          radius: area.radius_m, color: COLORS.area, weight: 2, dashArray: "6 6", fill: false
        }).addTo(group);
      }
      if (!(area.geometries || []).some(function (g) { return g.type === "Point"; })) {
        L.circleMarker(center, {
          radius: 5, color: COLORS.halo, weight: 2, fillColor: COLORS.center, fillOpacity: 1
        }).addTo(group);
      }
      if (area.amc) {
        var amc = [area.amc.lat, area.amc.lon];
        L.polyline([center, amc], { color: COLORS.amc, weight: 2, dashArray: "4 6" }).addTo(group);
        var marker = L.circleMarker(amc, {
          radius: 7, color: COLORS.halo, weight: 2, fillColor: COLORS.amc, fillOpacity: 1
        }).addTo(group);
        var label = area.amc.code + " · " + area.amc.name;
        if (area.amc.distance_km !== null && area.amc.distance_km !== undefined) {
          label += " · " + area.amc.distance_km + " " + ((i18n && i18n.km) || "km");
        }
        marker.bindTooltip(label);
      }
    } catch (error) {
      report("draw center", error);
    }
  }

  /* GeoJSON anida las posiciones a distinta profundidad según el tipo: se aplana hasta el par [lon, lat]. */
  function collect(coordinates, points) {
    if (!Array.isArray(coordinates)) {
      return;
    }
    if (typeof coordinates[0] === "number") {
      points.push([coordinates[1], coordinates[0]]);
      return;
    }
    coordinates.forEach(function (inner) { collect(inner, points); });
  }

  function bounds(areas) {
    var points = [];
    areas.forEach(function (area) {
      points.push(area.center);
      (area.geometries || []).forEach(function (geometry) {
        collect(geometry.coordinates, points);
      });
      if (area.amc) {
        points.push([area.amc.lat, area.amc.lon]);
      }
    });
    return points;
  }

  function build(container) {
    var L = window.L;
    if (!L) {
      fail(container, "Leaflet is not loaded", "leaflet");
      return;
    }
    var config;
    try {
      config = readConfig(container);
    } catch (error) {
      fail(container, error, "data");
      return;
    }
    var map;
    try {
      map = L.map(container, {
        scrollWheelZoom: false,
        dragging: !(L.Browser && L.Browser.mobile),
        attributionControl: true
      });
      addTiles(L, map, config.tiles);
      var group = L.layerGroup().addTo(map);
      config.areas.forEach(function (area) { drawArea(L, group, area, config.i18n); });
      var points = bounds(config.areas);
      var size = map.getSize();
      var movable = size.x > 0 && size.y > 0;
      if (movable && points.length) {
        map.fitBounds(points, { padding: [24, 24], maxZoom: 15, animate: false });
      } else if (movable && config.areas.length) {
        map.setView(config.areas[0].center, 12, { animate: false });
      }
      container.dataset.miniMapState = "ready";
    } catch (error) {
      fail(container, error, "map");
    }
  }

  /* El `<details>` va abierto en escritorio y cerrado en móvil: el mapa ocupa media pantalla y quien
     sólo quiere los datos no debería tener que desplazarse por él. */
  function openOnDesktop(details) {
    if (details && window.matchMedia && window.matchMedia(DESKTOP).matches) {
      details.open = true;
    }
  }

  function start(container) {
    if (container.dataset.miniMapState) {
      return;
    }
    container.dataset.miniMapState = "pending";
    var details = container.closest ? container.closest("details") : null;
    openOnDesktop(details);
    if (isVisible(container)) {
      build(container);
      return;
    }
    if (details) {
      var onToggle = function () {
        if (details.open && isVisible(container)) {
          details.removeEventListener("toggle", onToggle);
          build(container);
        }
      };
      details.addEventListener("toggle", onToggle);
      /* Abierto por `openOnDesktop` antes de que exista `toggle`: se vuelve a mirar al próximo cuadro. */
      if (details.open && typeof window.setTimeout === "function") {
        window.setTimeout(onToggle, 0);
      }
      return;
    }
    report("container", "hidden, not drawn");
  }

  function init(root) {
    var scope = root || document;
    if (!scope.querySelectorAll) {
      return;
    }
    Array.prototype.forEach.call(scope.querySelectorAll("[data-mini-map]"), start);
  }

  window.MiniMap = { init: init };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { init(document); });
  } else {
    init(document);
  }
  if (document.body && document.body.addEventListener) {
    /* El fragmento de la vista previa llega por htmx: su mapa se arma al insertarse. */
    document.body.addEventListener("htmx:afterSwap", function (event) {
      init(event.detail && event.detail.target ? event.detail.target : document);
    });
  }
})();
