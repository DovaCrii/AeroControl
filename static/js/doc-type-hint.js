/* LV-386: la ayuda bajo el selector de tipo de documento.
   El servidor ya dibuja la ayuda del valor inicial; esto sólo la actualiza al cambiar el tipo, leyendo
   los data-* de la opción elegida. Un único listener delegado: el formulario también llega por HTMX
   (modal) y el guard evita duplicarlo si el parcial se carga más de una vez. */
(function () {
  "use strict";
  if (window.docTypeHintReady) {
    return;
  }
  window.docTypeHintReady = true;

  function update(select) {
    var hint = document.getElementById("doc-type-hint");
    var option = select.options[select.selectedIndex];
    if (!hint || !option) {
      return;
    }
    var expiry = option.getAttribute("data-expiry");
    var description = option.getAttribute("data-description");
    hint.textContent = "";
    if (!option.value || !expiry) {
      hint.hidden = true;
      return;
    }
    var line = hint.getAttribute(expiry === "yes" ? "data-expiry-yes" : "data-expiry-no");
    var text = document.createElement("span");
    text.textContent = description ? description + " " + line : line;
    hint.appendChild(text);
    hint.hidden = false;
  }

  document.addEventListener("change", function (event) {
    var select = event.target;
    if (select && select.hasAttribute && select.hasAttribute("data-doc-type-select")) {
      update(select);
    }
  });
})();
