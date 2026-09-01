// LV-208: regular el ancho de la barra de navegación arrastrando su borde.
//
// Pedido del usuario: *"se podía poner que la navegación poder agrandar o
// desplazar para poder regular el ancho de la barra"*. La barra tenía dos
// estados —abierta o en modo icono— y nada en medio, así que con rótulos como
// "Planificación geoespacial" había que elegir entre texto en dos líneas y
// quitarle sitio al contenido. Colapsar resuelve otra cosa: ganar pantalla de un
// golpe, y sigue existiendo.
//
// Archivo aparte de `app.js` a propósito: `app.js` es el comportamiento base del
// layout y se carga en todas las páginas; esto es un solo control con su propio
// estado persistido, y mezclarlo habría engordado el archivo que más se lee.
(function () {
  'use strict';

  // Los límites, y por qué estos.
  //
  // `LV-170` midió que "Evaluación de conocimientos" pide 248 px y con el
  // relleno de la barra el mínimo para no recortar son 272. El mínimo de acá es
  // **más bajo a propósito**: quien arrastra está eligiendo, y por debajo de 272
  // los rótulos largos pasan a dos líneas —no se desbordan, el CSS no fija
  // `nowrap`— lo cual es un resultado legítimo si lo que se quiere es sitio para
  // el contenido. Los 240 son el punto donde el icono más el texto más corto
  // siguen conviviendo; por debajo el menú deja de ser un menú.
  //
  // El máximo evita el estado sin retorno: una barra de 900 px en una pantalla
  // de 1280 tapa el contenido y, si además se recuerda, la siguiente visita
  // abre así.
  var MIN = 240;
  var MAX = 420;
  var STORE_KEY = 'sidebar-width';
  // Cuánto mueve cada pulsación de flecha. 16 px es un paso que se nota sin
  // obligar a treinta pulsaciones para cruzar el rango.
  var STEP = 16;

  // `localStorage` lanza —no devuelve null— en una ventana privada o con las
  // cookies de sitio bloqueadas, así que cada acceso va envuelto. Es el mismo
  // cuidado que `LV-154` documentó para los borradores: un control de layout no
  // puede tumbar la página por no poder recordar un número.
  function readStored() {
    try {
      var raw = window.localStorage.getItem(STORE_KEY);
      if (!raw) return null;
      var value = parseInt(raw, 10);
      return isNaN(value) ? null : clamp(value);
    } catch (error) {
      return null;
    }
  }

  function store(value) {
    try {
      window.localStorage.setItem(STORE_KEY, String(value));
    } catch (error) {
      /* Sin almacenamiento el ancho vale para esta visita y no se recuerda,
         que es mejor que no poder ajustarlo. */
    }
  }

  function clamp(value) {
    return Math.min(MAX, Math.max(MIN, value));
  }

  // Se escribe en `documentElement` y **no** en el elemento de la barra: ver el
  // comentario de `--ac-sidebar-width` en `app.css`. Inline sobre `.sidebar`
  // ganaría por especificidad y anularía el ancho del estado colapsado, con lo
  // que el botón `<` dejaría de funcionar en cuanto alguien tocara el borde.
  function apply(value, grip) {
    document.documentElement.style.setProperty(
      '--ac-sidebar-width-user',
      value + 'px'
    );
    if (grip) grip.setAttribute('aria-valuenow', String(value));
  }

  function currentWidth(sidebar) {
    var stored = readStored();
    if (stored !== null) return stored;
    // Sin valor guardado, el ancho real que el CSS está aplicando — no un 280
    // repetido acá, que se desincronizaría del token el día que cambie.
    return clamp(Math.round(sidebar.getBoundingClientRect().width));
  }

  function setUp() {
    var sidebar = document.getElementById('sidebar');
    var grip = document.querySelector('.sidebar-resizer');
    if (!sidebar || !grip) return;

    grip.setAttribute('aria-valuemin', String(MIN));
    grip.setAttribute('aria-valuemax', String(MAX));

    // El ancho recordado se aplica al cargar, y sólo en escritorio: en móvil la
    // barra es un cajón de `min(86vw, ...)` y un ancho de usuario no significa
    // nada ahí.
    var stored = readStored();
    if (stored !== null && window.innerWidth >= 769) apply(stored, grip);
    else grip.setAttribute('aria-valuenow', String(currentWidth(sidebar)));

    var startX = 0;
    var startWidth = 0;
    var dragging = false;

    function onMove(event) {
      if (!dragging) return;
      // El borde derecho crece hacia la derecha, así que el delta se suma.
      apply(clamp(startWidth + (event.clientX - startX)), grip);
    }

    function onUp() {
      if (!dragging) return;
      dragging = false;
      document.body.classList.remove('is-resizing-sidebar');
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      // Se guarda al soltar y no en cada píxel: escribir en `localStorage` en
      // cada `pointermove` son cientos de escrituras sincrónicas por arrastre.
      store(clamp(Math.round(sidebar.getBoundingClientRect().width)));
    }

    grip.addEventListener('pointerdown', function (event) {
      // Sólo el botón principal: un arrastre con el botón derecho abriría el
      // menú contextual a medio camino y dejaría el estado colgado.
      if (event.button !== 0) return;
      dragging = true;
      startX = event.clientX;
      startWidth = sidebar.getBoundingClientRect().width;
      document.body.classList.add('is-resizing-sidebar');
      // `pointermove` en `window` y no en el tirador: el puntero se adelanta al
      // elemento durante un arrastre rápido y los eventos se perderían.
      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
      event.preventDefault();
    });

    // **La alternativa de teclado no es un extra.** Un control que sólo responde
    // al ratón es inalcanzable para quien navega con tabulador, y `LV-185` dejó
    // el precedente de medir la accesibilidad antes de dar un cambio visual por
    // bueno. Con `role="separator"` y `tabindex`, las flechas son lo que un
    // lector de pantalla anuncia como forma de moverlo.
    grip.addEventListener('keydown', function (event) {
      var width = currentWidth(sidebar);
      var next = null;
      if (event.key === 'ArrowLeft') next = width - STEP;
      else if (event.key === 'ArrowRight') next = width + STEP;
      else if (event.key === 'Home') next = MIN;
      else if (event.key === 'End') next = MAX;
      if (next === null) return;
      next = clamp(next);
      apply(next, grip);
      store(next);
      // Las flechas desplazan la página por defecto, y acá ya significan otra
      // cosa.
      event.preventDefault();
    });

    // El valor anunciado se refresca al enfocar, y no es un detalle de más:
    // medido en el navegador, `aria-valuenow` decía 240 con la barra en 280.
    // Se había calculado al cargar la página —cuando el viewport era estrecho y
    // la barra era el cajón móvil— y nadie lo volvía a tocar, así que un lector
    // de pantalla anunciaba un ancho que no era el de la pantalla. Al enfocar es
    // el momento exacto en que el número importa: es cuando alguien va a usar las
    // flechas. Se prefiere esto a escuchar `resize`, que dispara decenas de veces
    // por arrastre de ventana para mantener al día un número que sólo se lee
    // cuando el control tiene el foco.
    grip.addEventListener('focus', function () {
      grip.setAttribute(
        'aria-valuenow',
        String(Math.round(sidebar.getBoundingClientRect().width))
      );
    });

    // Doble clic vuelve al ancho por defecto. Es la salida rápida del ajuste que
    // quedó mal, sin obligar a arrastrar de vuelta buscando el punto original.
    grip.addEventListener('dblclick', function () {
      document.documentElement.style.removeProperty('--ac-sidebar-width-user');
      try {
        window.localStorage.removeItem(STORE_KEY);
      } catch (error) {
        /* ver `store` */
      }
      grip.setAttribute(
        'aria-valuenow',
        String(Math.round(sidebar.getBoundingClientRect().width))
      );
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setUp);
  } else {
    setUp();
  }
})();
