// LV-398: la tarjeta «¿Recién llega a AeroControl?» del panel se puede cerrar, y el
// cierre se recuerda en este navegador.
//
// Va sin `defer`, justo después de la tarjeta: así quien ya la cerró no la ve
// aparecer y desaparecer al cargar. Sin JS la tarjeta se ve siempre y el botón de
// cerrar no aparece (nace con `hidden`).
//
// ⚠️ **Los dos accesos a `localStorage` van envueltos, lectura incluida.** En una
// ventana privada o con el almacenamiento de sitio bloqueado `localStorage`
// **lanza** —no devuelve `null`— y una excepción acá cortaría la función a medio
// camino (la lección de `app.js` y `theme-init.js` en `AGENTS.md`). Si no se puede
// guardar, la tarjeta igual se oculta en esta visita y vuelve en la siguiente.
(function () {
  var KEY = 'ac-start-card-hidden';

  function readHidden() {
    try {
      return localStorage.getItem(KEY) === '1';
    } catch (error) {
      return false;
    }
  }

  function rememberHidden() {
    try {
      localStorage.setItem(KEY, '1');
    } catch (error) {
      // Sin almacenamiento: se oculta sólo en esta visita.
    }
  }

  // `d-none` además de `hidden`: el atributo pierde contra `d-flex` (LV-209).
  function hide(element) {
    element.hidden = true;
    element.classList.add('d-none');
  }

  function show(element) {
    element.hidden = false;
    element.classList.remove('d-none');
  }

  var card = document.querySelector('[data-start-card]');
  if (!card) {
    return;
  }
  if (readHidden()) {
    hide(card);
    return;
  }
  var dismiss = card.querySelector('[data-start-card-dismiss]');
  if (!dismiss) {
    return;
  }
  show(dismiss);
  dismiss.addEventListener('click', function () {
    rememberHidden();
    hide(card);
    // El foco no se queda en un botón que ya no existe: vuelve al contenido.
    var main = document.getElementById('main-content');
    if (main) {
      main.focus();
    }
  });
})();
