// Set the colour theme before first paint to avoid a flash of the wrong theme.
// Extracted from an inline <script> so the page needs no 'unsafe-inline' in the
// Content-Security-Policy (MASTER_PLAN V.10). Must stay render-blocking in the
// document <head>.
//
// `UX-08` suma acá la densidad de las tablas, por lo mismo que el tema: es un
// atributo en `<html>` que decide el alto de cada fila, y ponerlo después de
// pintar haría saltar la lista entera a la vista.
//
// ⚠️ **Los dos accesos van envueltos, y no es prolijidad.** `localStorage`
// **lanza** —no devuelve `null`— en una ventana privada o con el almacenamiento
// de sitio bloqueado. Este archivo era el único de los cuatro con JS del
// proyecto que leía sin `try`, y es el que corre **primero en cada página**: la
// excepción abortaba el resto de la función, así que `data-theme` no se ponía y
// quien prefiere el tema oscuro veía la aplicación en claro, en todas las
// pantallas, sin forma de saber por qué. Es exactamente la lección que
// `AGENTS.md` ya tenía escrita de cuando pasó en `app.js`.
(function () {
  function stored(key) {
    try {
      return localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  var h = document.documentElement;

  var t = stored('theme');
  if (!t) {
    t = window.matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light';
  }
  h.setAttribute('data-theme', t);
  h.setAttribute('data-bs-theme', t);

  // Sin preferencia guardada, cómoda: es la densidad que la aplicación ha
  // tenido siempre, y estrenar a alguien en compacta sería cambiarle la
  // pantalla sin que lo pidiera.
  if (stored('density') === 'compact') {
    h.setAttribute('data-density', 'compact');
  }
})();
