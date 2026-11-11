/* LV-430: botón «Print / Save as PDF» del reporte de vuelo. Reencuadra el mapa satelital
   (flight-analysis.js deja `#fa-map._fa`) y espera a que carguen las teselas antes de abrir el
   diálogo de impresión; si no cargan a tiempo imprime igual (límite de 2,5 s). */
(function () {
  "use strict";

  var WAIT_MS = 2500;
  var SETTLE_MS = 400;

  function frame() {
    var fa = (document.getElementById("fa-map") || {})._fa;
    if (!fa) { return null; }
    try {
      fa.map.invalidateSize();
      fa.map.fitBounds(fa.bounds, { padding: [24, 24], animate: false });
    } catch (error) {
      if (window.console && window.console.error) { window.console.error("flight-report: " + error.message); }
    }
    return fa;
  }

  function printWhenReady() {
    var fa = frame();
    var done = false;
    function go() {
      if (done) { return; }
      done = true;
      window.setTimeout(function () { window.print(); }, SETTLE_MS);
    }
    if (fa && fa.base && fa.base.once) { fa.base.once("load", go); }
    /* Con las teselas ya en pantalla `load` no se repite: el plazo cubre ese caso. */
    window.setTimeout(go, fa ? WAIT_MS : 0);
  }

  window.addEventListener("beforeprint", frame);
  var button = document.getElementById("fr-print");
  if (button) { button.addEventListener("click", printWhenReady); }
})();
