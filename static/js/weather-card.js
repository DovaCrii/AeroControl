/* LV-353: la tarjeta del tiempo no se queda en «cargando» para siempre.
 *
 * htmx no reemplaza la respuesta si la petición falla por red o responde 4xx/5xx, así que el
 * esqueleto de carga quedaba en pantalla sin salida (y un `hx-on` inline lo bloquea la CSP).
 * Aquí se escuchan los tres eventos de fallo y se cambia el hueco por el estado de error que
 * ya existe («forecast unavailable» + Reintentar), tomado del <template data-wx-error> que el
 * panel dibuja dentro del hueco. No hay red nueva: reintentar es el mismo `hx-get` del botón.
 */
(function () {
  "use strict";

  var SLOT_ID = "wx-card";
  var errorTemplate = null; // se guarda la primera vez: el hueco original ya no estará después

  function slotFor(event) {
    var element = (event.detail && event.detail.elt) || event.target;
    if (!element || !element.closest) {
      return null;
    }
    return element.closest("#" + SLOT_ID);
  }

  function showError(event) {
    var slot = slotFor(event);
    if (!slot || !slot.parentNode) {
      return;
    }
    var template = slot.querySelector("template[data-wx-error]");
    if (template) {
      errorTemplate = template;
    }
    if (!errorTemplate) {
      return;
    }
    var fresh = errorTemplate.content.firstElementChild;
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
