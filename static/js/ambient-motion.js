/* LV-321: pausa el movimiento ambiental (portada) cuando no se ve: fuera de pantalla o con la pestaña oculta.
   LV-348: también el que llega por htmx (tarjeta del tiempo, panel del asistente): se re-escanea en
   `htmx:afterSwap`/`htmx:load` y sólo se observan los nodos nuevos. Sin dependencias ni red; si falta
   este script, las animaciones simplemente siguen. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  if (reduce && reduce.matches) return; // el CSS ya no anima: nada que pausar
  var nodes = new Set();
  var onscreen = new Map();
  var observer = null;
  function apply(node) {
    node.classList.toggle("is-paused", document.hidden || onscreen.get(node) === false);
  }
  function applyAll() {
    nodes.forEach(function (n) {
      if (!n.isConnected) { nodes.delete(n); onscreen.delete(n); return; }
      apply(n);
    });
  }
  if ("IntersectionObserver" in window) {
    observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { onscreen.set(e.target, e.isIntersecting); apply(e.target); });
    });
  }
  function scan(root) {
    if (!root || !root.querySelectorAll) root = document;
    var found = [];
    if (root.matches && root.matches("[data-ambient]")) found.push(root);
    found.push.apply(found, root.querySelectorAll("[data-ambient]"));
    found.forEach(function (n) {
      if (nodes.has(n)) return; // ya observado: sin observers duplicados
      nodes.add(n);
      if (observer) observer.observe(n);
      apply(n);
    });
  }
  function onHtmx(event) {
    scan((event.detail && event.detail.elt) || event.target);
  }
  scan(document);
  document.addEventListener("visibilitychange", applyAll);
  document.addEventListener("htmx:afterSwap", onHtmx);
  document.addEventListener("htmx:load", onHtmx);
})();
