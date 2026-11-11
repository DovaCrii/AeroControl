/* LV-431: las aeronaves y los permisos del alta de un log se acotan al centro de costo elegido.
   Es sólo una comodidad: sin JS el formulario ofrece todo y el servidor valida igual. */
(function () {
  "use strict";

  function filter(select, centre) {
    var options = select.querySelectorAll("option[data-cc]");
    for (var i = 0; i < options.length; i++) {
      var hidden = centre !== "" && options[i].getAttribute("data-cc") !== centre;
      options[i].hidden = hidden;
      options[i].disabled = hidden;
    }
    var chosen = select.options[select.selectedIndex];
    if (chosen && chosen.disabled) {
      select.value = "";
    }
  }

  function init() {
    var followers = document.querySelectorAll("select[data-cc-follows]");
    for (var i = 0; i < followers.length; i++) {
      (function (select) {
        var source = document.getElementById(select.getAttribute("data-cc-follows"));
        if (!source) {
          return;
        }
        source.addEventListener("change", function () {
          filter(select, source.value);
        });
        filter(select, source.value);
      })(followers[i]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
