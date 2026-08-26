/* LV-149: copiar al portapapeles un valor de "Datos para SIGO".

   El trabajo real con estos datos es transcribir casilla por casilla en el
   formulario del Estado, y una coordenada mal tipeada no se nota hasta que
   alguien mira el mapa. Un botón por casilla es lo que evita ese error.

   Sin texto en este archivo: las etiquetas viajan en `data-label-*` desde la
   plantilla, que es donde vive `{% translate %}`. Un literal acá quedaría en
   inglés en una interfaz en español y `makemessages` no lo vería.

   Delegación en `document` y no en la tarjeta: los valores se dibujan también
   en la ficha de la solicitud, y una respuesta HTMX reemplaza nodos -- un
   listener por botón se pierde en el reemplazo. */
(function () {
  "use strict";

  var RESET_MS = 1500;
  var CLEAR_MS = 4000;

  function announce(button, message) {
    var region = document.getElementById(button.dataset.copyStatus || "copy-status");
    if (!region || !message) {
      return;
    }
    region.textContent = message;
    window.setTimeout(function () {
      if (region.textContent === message) {
        region.textContent = "";
      }
    }, CLEAR_MS);
  }

  /* `navigator.clipboard` sólo existe en contexto seguro, y esta aplicación se
     sirve por http en la intranet: sin este respaldo el botón no haría nada en
     el único lugar donde se usa. */
  function legacyCopy(text) {
    var field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.top = "-1000px";
    document.body.appendChild(field);
    field.select();
    var copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }
    document.body.removeChild(field);
    return copied;
  }

  function feedback(button, copied) {
    announce(button, copied ? button.dataset.labelCopied : button.dataset.labelFailed);
    if (!copied) {
      return;
    }
    button.classList.add("is-copied");
    window.setTimeout(function () {
      button.classList.remove("is-copied");
    }, RESET_MS);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy]");
    if (!button) {
      return;
    }
    event.preventDefault();
    var text = button.dataset.copy;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () {
          feedback(button, true);
        },
        function () {
          feedback(button, legacyCopy(text));
        }
      );
      return;
    }
    feedback(button, legacyCopy(text));
  });
})();
