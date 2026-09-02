/* La pantalla de acceso: mostrar la contraseña y avisar del Bloq Mayús.
 *
 * Las dos cosas atacan el mismo problema y por eso van juntas: **a los cinco
 * intentos fallidos `django-axes` retiene la cuenta quince minutos**, así que
 * escribir a ciegas no cuesta un intento, cuesta la mañana. Con guantes y un
 * teclado táctil en faena, además, es lo normal.
 *
 * Sin dependencias y sin JS en línea: la política de seguridad de contenido de
 * esta aplicación prohíbe `unsafe-inline` en `script-src`, así que un
 * `onclick=` en la plantilla no se ejecutaría y el botón sería un adorno.
 */
(function () {
  "use strict";

  var password = document.getElementById("id_password");
  if (!password) {
    return;
  }

  var reveal = document.getElementById("login-reveal");
  if (reveal) {
    reveal.addEventListener("click", function () {
      var shown = password.type === "text";
      password.type = shown ? "password" : "text";
      reveal.textContent = shown ? reveal.dataset.show : reveal.dataset.hide;
      reveal.setAttribute("aria-pressed", shown ? "false" : "true");
      // El foco vuelve al campo: quien apretó "mostrar" estaba escribiendo, y
      // dejarlo en el botón obliga a volver con el mouse.
      password.focus();
    });
  }

  var caps = document.getElementById("login-caps");
  if (!caps) {
    return;
  }

  // `getModifierState` no existe en todos los eventos ni en todos los
  // navegadores; sin él, el aviso simplemente no aparece — nunca aparece al
  // revés, que sería peor que no tenerlo.
  function sync(event) {
    if (typeof event.getModifierState !== "function") {
      return;
    }
    caps.hidden = !event.getModifierState("CapsLock");
  }

  password.addEventListener("keydown", sync);
  password.addEventListener("keyup", sync);
  // Al salir del campo el aviso se va: fuera de él no hay nada que corregir, y
  // un aviso que se queda colgado enseña a no mirarlo.
  password.addEventListener("blur", function () {
    caps.hidden = true;
  });
})();
