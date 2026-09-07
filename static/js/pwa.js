// `UX-26` · Registrar el *service worker*, y decir cuándo lo que se está
// mirando no es de ahora.
//
// El criterio de la fila: *"en avión o sin señal se puede consultar la última
// ficha de aeronave vista"* — y **marcada claramente como «datos del <fecha>»**.
// Esa segunda mitad es la que este archivo resuelve, y es la que importa: una
// aplicación que muestra vencimientos sirviendo una pantalla de ayer sin decirlo
// no está degradando con gracia, está mintiendo con buena letra.
//
// **La fecha se lee de la caché, no del reloj ni del servidor.** `sw.js` sella
// cada respuesta que guarda con `X-Aero-Cached-At`; acá se busca la entrada de
// esta misma URL y se lee ese sello. Deducirla de la cabecera `Date` habría dado
// la hora en que el servidor generó la página, que puede ser muy anterior a
// cuando esta persona la miró.
//
// Sin texto propio: los rótulos llegan traducidos en `data-*`, como en el resto
// de las islas de este proyecto.
(function () {
  "use strict";

  if (!("serviceWorker" in navigator)) return;

  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").catch(function () {
      // Un registro fallido no es un error que mostrar: la aplicación funciona
      // igual, sólo que sin la copia sin señal. Callarlo es correcto; lo que no
      // sería correcto es que la página se rompiera por esto.
    });
  });

  // ⚠️ Cerrar sesión se lleva lo guardado. Es la contrapartida de guardar fichas
  // de personas y aeronaves en el navegador: en un equipo compartido en faena,
  // cerrar sesión tiene que llevarse lo que se vio. El mensaje se manda **antes**
  // de que el formulario navegue; el worker lo procesa con `waitUntil`, así que
  // sobrevive a que la página se vaya.
  document.body.addEventListener("submit", function (event) {
    var form = event.target.closest('form[action*="logout"]');
    if (form && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage("aero-clear-cache");
    }
  });

  announceIfStale();

  async function announceIfStale() {
    var banner = document.getElementById("offline-banner");
    if (!banner || !("caches" in window)) return;
    // Sólo cuando el navegador **afirma** que no hay red. `navigator.onLine` es
    // optimista en el otro sentido —un `true` no garantiza que haya internet—
    // pero un `false` es fiable, y ése es el único caso en que esta página pudo
    // haber salido de la caché.
    if (navigator.onLine) return;
    try {
      var hit = await caches.match(window.location.href);
      if (!hit) return;
      var when = hit.headers.get("X-Aero-Cached-At");
      if (!when) return;
      var label = banner.dataset.staleLabel || "";
      banner.textContent = label.replace(
        "%(when)s",
        new Date(when).toLocaleString(),
      );
      banner.hidden = false;
      // `d-none` además del atributo, por lo mismo de siempre en este proyecto:
      // `[hidden]` pierde contra las utilidades de Bootstrap que ponen `display`
      // con `!important` (`LV-209`).
      banner.classList.remove("d-none");
    } catch (error) {
      // Sin caché legible no hay nada que anunciar, y una excepción acá no puede
      // llevarse la página: quien está sin señal ya tiene bastante.
    }
  }
})();
