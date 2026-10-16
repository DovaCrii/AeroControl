/* LV-321: pausa el movimiento ambiental (portada) cuando no se ve: fuera de pantalla o con la pestaña oculta.
   Sin dependencias ni red; si falta este script, las animaciones simplemente siguen. */
(function () {
  "use strict";
  var nodes = document.querySelectorAll("[data-ambient]");
  if (!nodes.length) return;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  if (reduce && reduce.matches) return; // el CSS ya no anima: nada que pausar
  var onscreen = new Map();
  function apply(node) {
    node.classList.toggle("is-paused", document.hidden || onscreen.get(node) === false);
  }
  function applyAll() { nodes.forEach(apply); }
  if ("IntersectionObserver" in window) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { onscreen.set(e.target, e.isIntersecting); apply(e.target); });
    });
    nodes.forEach(function (n) { observer.observe(n); });
  }
  document.addEventListener("visibilitychange", applyAll);
})();
