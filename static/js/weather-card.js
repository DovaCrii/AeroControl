/* LV-353: la tarjeta del tiempo no se queda en «cargando» para siempre.
 * LV-358 (E2): lo mismo vale para la franja «Entorno hoy» del panel.
 *
 * htmx no reemplaza la respuesta si la petición falla por red o responde 4xx/5xx, así que el
 * esqueleto de carga quedaba en pantalla sin salida (y un `hx-on` inline lo bloquea la CSP).
 * Aquí se escuchan los tres eventos de fallo y se cambia el hueco por el estado de error que
 * ya existe (mensaje + Reintentar), tomado del <template data-wx-error> que la página dibuja
 * dentro del hueco. No hay red nueva: reintentar es el mismo `hx-get` del botón.
 *
 * Sirve a cualquier hueco de la lista SLOT_IDS (la tarjeta del tiempo y la franja); cada uno
 * guarda su propio estado de error porque el hueco original ya no estará después.
 */
(function () {
  "use strict";

  var SLOT_IDS = ["wx-card", "env-strip"];
  var SELECTOR = SLOT_IDS.map(function (id) { return "#" + id; }).join(", ");
  var errorTemplates = {}; // id del hueco -> su <template>, guardado la primera vez

  function slotFor(event) {
    var element = (event.detail && event.detail.elt) || event.target;
    if (!element || !element.closest) {
      return null;
    }
    return element.closest(SELECTOR);
  }

  function showError(event) {
    var slot = slotFor(event);
    if (!slot || !slot.parentNode) {
      return;
    }
    var template = slot.querySelector("template[data-wx-error]");
    if (template) {
      errorTemplates[slot.id] = template;
    }
    var saved = errorTemplates[slot.id];
    if (!saved) {
      return;
    }
    var fresh = saved.content.firstElementChild;
    if (!fresh) {
      return;
    }
    var node = fresh.cloneNode(true);
    slot.replaceWith(node);
    if (window.htmx) {
      window.htmx.process(node); // activa el hx-get del botón Reintentar
    }
  }

  ["htmx:responseError", "htmx:sendError", "htmx:timeout"].forEach(function (name) {
    document.addEventListener(name, showError);
  });
})();
