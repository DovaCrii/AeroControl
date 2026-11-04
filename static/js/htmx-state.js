// LV-419 (UX T10): estado de carga y de error de htmx, global.
//
// Antes, una búsqueda en vivo sólo decía "Buscando…" y, si el servidor
// respondía 500, la tabla vieja se quedaba en pantalla sin aviso alguno: se
// leía como "no hay resultados nuevos". Acá se hacen dos cosas, ambas fuera del
// camino de la respuesta (nada de esto puede impedir un swap):
//
//  * Mientras dura la petición, el destino lleva `aria-busy="true"` y la clase
//    `.is-loading` (ver `htmx-state.css`). Se cuenta por elemento porque la
//    búsqueda en vivo dispara una petición nueva antes de que termine la
//    anterior: sin contador, la primera en terminar apagaría el estado de la
//    segunda.
//  * Si la petición falla (error HTTP no manejado, red caída, tiempo agotado) se
//    escribe un mensaje en la región viva `#htmx-status` de `base.html`. El
//    texto viene del atributo `data-error-label` de esa región, ya traducido por
//    la plantilla: este archivo no lleva texto visible. El 422 de los
//    formularios inválidos NO pasa por acá: `app.js` lo marca `isError = false`
//    y se pinta como formulario con errores.
(function () {
  'use strict';

  var pending = new WeakMap();
  var clearTimer = null;
  var HIDE_AFTER_MS = 10000;

  function mark(target) {
    if (!target || !target.setAttribute) return;
    pending.set(target, (pending.get(target) || 0) + 1);
    target.setAttribute('aria-busy', 'true');
    target.classList.add('is-loading');
  }

  function unmark(target) {
    if (!target || !target.removeAttribute) return;
    var left = (pending.get(target) || 1) - 1;
    if (left > 0) {
      pending.set(target, left);
      return;
    }
    pending.delete(target);
    target.removeAttribute('aria-busy');
    target.classList.remove('is-loading');
  }

  function announceError() {
    var region = document.getElementById('htmx-status');
    if (!region) return;
    var label = region.dataset.errorLabel;
    if (!label) return;
    // Vaciar y volver a escribir: un lector de pantalla no repite un texto que
    // no cambió, y el segundo fallo seguido también hay que anunciarlo.
    region.textContent = '';
    window.setTimeout(function () {
      region.textContent = label;
    }, 50);
    window.clearTimeout(clearTimer);
    clearTimer = window.setTimeout(function () {
      region.textContent = '';
    }, HIDE_AFTER_MS);
  }

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    mark(event.detail.target);
  });
  document.body.addEventListener('htmx:afterRequest', function (event) {
    unmark(event.detail.target);
  });
  document.body.addEventListener('htmx:sendAbort', function (event) {
    unmark(event.detail.target);
  });
  document.body.addEventListener('htmx:responseError', announceError);
  document.body.addEventListener('htmx:sendError', announceError);
  document.body.addEventListener('htmx:timeout', announceError);
})();
