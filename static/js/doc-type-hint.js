/* LV-386: la ayuda bajo el selector de tipo de documento.
   El servidor ya dibuja la ayuda del valor inicial; esto sólo la actualiza al cambiar el tipo, leyendo
   los data-* de la opción elegida. Un único listener delegado: el formulario también llega por HTMX
   (modal) y el guard evita duplicarlo si el parcial se carga más de una vez.
   LV-395: si el tipo no pide fecha de emisión (data-issue="no") se oculta el campo marcado con
   data-issue-date-field y la ayuda lo avisa. Sin JS el campo queda visible y opcional. */
(function () {
  "use strict";
  if (window.docTypeHintReady) {
    return;
  }
  window.docTypeHintReady = true;

  function toggleIssueDate(select, hidden) {
    var form = select.form || document;
    var fields = form.querySelectorAll("[data-issue-date-field]");
    for (var i = 0; i < fields.length; i++) {
      fields[i].hidden = hidden;
    }
  }

  function update(select) {
    var hint = document.getElementById("doc-type-hint");
    var option = select.options[select.selectedIndex];
    if (!hint || !option) {
      return;
    }
    var expiry = option.getAttribute("data-expiry");
    var issue = option.getAttribute("data-issue");
    var description = option.getAttribute("data-description");
    hint.textContent = "";
    toggleIssueDate(select, !!option.value && issue === "no");
    if (!option.value || !expiry) {
      hint.hidden = true;
      return;
    }
    var parts = [];
    if (description) {
      parts.push(description);
    }
    parts.push(hint.getAttribute(expiry === "yes" ? "data-expiry-yes" : "data-expiry-no"));
    if (issue === "no") {
      parts.push(hint.getAttribute("data-issue-no"));
    }
    var text = document.createElement("span");
    text.textContent = parts.join(" ");
    hint.appendChild(text);
    hint.hidden = false;
  }

  function syncAll(root) {
    var selects = (root || document).querySelectorAll("select[data-doc-type-select]");
    for (var i = 0; i < selects.length; i++) {
      toggleIssueDate(selects[i], selects[i].value !== "" &&
        selects[i].options[selects[i].selectedIndex].getAttribute("data-issue") === "no");
    }
  }

  document.addEventListener("change", function (event) {
    var select = event.target;
    if (select && select.hasAttribute && select.hasAttribute("data-doc-type-select")) {
      update(select);
    }
  });

  /* El tipo ya elegido al abrir (reemplazo, o un tipo precargado) también esconde el campo. */
  document.addEventListener("DOMContentLoaded", function () { syncAll(document); });
  document.addEventListener("htmx:load", function (event) { syncAll(event.target); });
  syncAll(document);
})();
