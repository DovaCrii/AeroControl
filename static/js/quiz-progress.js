/* LV-163: el avance de la prueba de conocimientos.

   Con 25 preguntas en una sola página no hay forma de saber si terminaste sin
   volver a subir a contarlas. La barra responde eso, y el aviso al enviar
   responde la otra mitad: una pregunta sin responder cuenta como incorrecta
   (`assessments.grade`), así que enviar con seis en blanco es tirar el intento
   sin haberlo decidido.

   Sin texto en este archivo: las etiquetas viajan en `data-label-*` desde la
   plantilla, que es donde vive `{% translate %}`. Un literal acá queda en
   inglés en una interfaz en español y `makemessages` no lo ve.

   Delegación en el formulario y no un listener por radio: son 100 controles, y
   uno por cada uno es cien veces el mismo cierre para un contador. */
(function () {
  "use strict";

  var form = document.getElementById("quiz-form");
  if (!form) {
    return;
  }
  var footer = form.querySelector(".quiz-footer");
  var fill = form.querySelector(".quiz-progress-fill");
  var text = form.querySelector(".quiz-progress-text");
  if (!footer || !fill || !text) {
    return;
  }

  var total = parseInt(footer.dataset.total, 10) || 0;

  /* Cuántos grupos de radios tienen una opción marcada. Se cuenta por `name`
     -- un grupo es una pregunta -- y no por radios marcados, que da lo mismo
     hoy y dejaría de darlo el día que una pregunta admita varias. */
  function answered() {
    var names = {};
    var inputs = form.querySelectorAll(".quiz-option-input");
    for (var i = 0; i < inputs.length; i += 1) {
      if (inputs[i].checked) {
        names[inputs[i].name] = true;
      }
    }
    return Object.keys(names).length;
  }

  function render() {
    var done = answered();
    var percent = total ? Math.round((done / total) * 100) : 0;
    fill.style.width = percent + "%";
    text.textContent = done + " / " + total;
    footer.classList.toggle("is-complete", total > 0 && done === total);
  }

  form.addEventListener("change", function (event) {
    if (event.target.classList.contains("quiz-option-input")) {
      render();
    }
  });

  /* Confirmar sólo cuando de verdad falta algo. Un `confirm` en cada envío se
     aprende a descartar sin leerlo, y entonces deja de avisar. */
  form.addEventListener("submit", function (event) {
    var missing = total - answered();
    if (missing <= 0) {
      return;
    }
    /* `{count}` y no `%(count)s`: makemessages duplica el `%` literal al
       extraer de una plantilla, así que la cadena con esa forma nunca calza con
       el catálogo y sale en inglés. */
    var label = footer.dataset.labelRemaining || "";
    if (!window.confirm(label.replace("{count}", missing))) {
      event.preventDefault();
    }
  });

  render();
})();
