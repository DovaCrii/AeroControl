/* LV-368 (fase 5): el selector de plan del formulario del permiso, con su vista previa y su modal de importación.

   Hace dos cosas y ninguna es rellenar casillas (se mantiene LV-153: el relleno ocurre al guardar):
   1. htmx pide la vista previa con el parámetro `source_plan`, que es el nombre del campo del formulario;
      la vista la espera como `plan`. Se renombra al armar la petición (`htmx:configRequest`), sin `eval`:
      la CSP no admite `unsafe-eval`, así que nada de `hx-vals="js:…"`.
   2. Al terminar el modal «Subir un KMZ nuevo», el servidor emite `geoplan-imported` con el plan recién
      creado: se agrega al selector, se elige y se avisa el cambio, que dispara la vista previa. */
(function () {
  "use strict";

  function report(where, error) {
    if (window.console && window.console.error) {
      window.console.error("plan-picker: " + where + ": " + (error && error.message ? error.message : error));
    }
  }

  function renameParameter(event) {
    var element = event.detail && event.detail.elt;
    if (!element || !element.hasAttribute || !element.hasAttribute("data-plan-picker-select")) {
      return;
    }
    try {
      var parameters = event.detail.parameters;
      var value = typeof parameters.get === "function" ? parameters.get("source_plan") : parameters.source_plan;
      if (typeof parameters.set === "function") {
        parameters.set("plan", value || "");
        parameters["delete"]("source_plan");
      } else {
        parameters.plan = value || "";
        delete parameters.source_plan;
      }
    } catch (error) {
      report("request", error);
    }
  }

  function selectImported(event) {
    var plan = event.detail || {};
    var select = document.querySelector("[data-plan-picker-select]");
    if (!select || !plan.id) {
      report("imported", "no selector or no plan in the event");
      return;
    }
    var exists = Array.prototype.some.call(select.options, function (option) { return option.value === plan.id; });
    if (!exists) {
      var option = document.createElement("option");
      option.value = plan.id;
      option.textContent = plan.label || plan.id;
      select.appendChild(option);
    }
    select.value = plan.id;
    /* El cambio es lo que htmx escucha: pide la vista previa del plan recién importado. */
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  if (document.body && document.body.addEventListener) {
    document.body.addEventListener("htmx:configRequest", renameParameter);
    document.body.addEventListener("geoplan-imported", selectImported);
  }
})();
