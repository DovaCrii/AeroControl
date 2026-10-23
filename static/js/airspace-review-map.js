/* LV-361 (fase 4): mini-mapa de sólo lectura de la revisión de una zona del AIP.

   Dibuja la geometría propuesta (línea continua) y la de Google (punteada) sobre un lienzo sin
   fondo: ninguna llamada externa. Los datos vienen de `json_script` (inertes) y no se interpolan
   como HTML. El mapa no se puede editar: la corrección se hace en el formulario, con validación del
   servidor. Leaflet se carga como script clásico antes que éste (`L` es global). */
(function () {
  "use strict";

  var node = document.getElementById("air-review-data");
  var holder = document.getElementById("air-review-map");
  if (!node || !holder || !window.L) {
    return;
  }
  var data;
  try {
    data = JSON.parse(node.textContent);
  } catch (error) {
    if (window.console && console.error) {
      console.error("airspace-review-map: bad data: " + error.message);
    }
    return;
  }

  var map = L.map(holder, {
    zoomControl: true,
    attributionControl: false,
    scrollWheelZoom: false,
    keyboard: true,
  });

  var layers = [];
  function draw(geometry, className) {
    if (!geometry) {
      return;
    }
    layers.push(
      L.geoJSON(geometry, {
        style: function () {
          return { className: className };
        },
        interactive: false,
      }).addTo(map)
    );
  }

  draw(data.google, "air-review-google");
  draw(data.aip, "air-review-aip");

  var bounds = null;
  layers.forEach(function (layer) {
    var box = layer.getBounds();
    if (box.isValid()) {
      bounds = bounds ? bounds.extend(box) : box;
    }
  });
  if (bounds) {
    map.fitBounds(bounds, { padding: [24, 24] });
  } else {
    map.setView([-33.45, -70.65], 5);
  }
})();
