// `UX-25` · La paleta de comandos (`Ctrl/⌘+K`), y con ella la búsqueda móvil de
// `UX-24`.
//
// Quien trabaja alertas entra veinte veces al día y hoy cada entrada cuesta
// abrir el menú, buscar el grupo y encontrar el renglón. Y bajo 768 px la
// búsqueda global desaparecía sin dejar nada en su lugar: en el teléfono, que es
// donde se trabaja en faena, la aplicación no tenía búsqueda.
//
// **Los destinos se leen del menú lateral, en el momento de abrir.** No es
// pereza: el menú ya esconde lo que esta persona no puede ver, así que la paleta
// hereda los permisos sin preguntarle nada al servidor, y no hay una segunda
// lista que se desincronice el día que alguien agregue una pantalla. Una lista
// propia habría terminado ofreciendo rutas que van a un 403 — que es `LV-130`,
// enseñar a desconfiar de la pantalla.
//
// Sin texto en este archivo: los rótulos llegan traducidos en `data-*`. Sin JS
// inline: la CSP es `script-src 'self'`.
(function () {
  'use strict';

  var palette = document.getElementById('command-palette');
  if (!palette) return;

  var input = document.getElementById('command-palette-input');
  var results = document.getElementById('command-palette-results');
  var opener = null;
  var entries = [];
  var active = 0;

  function readMenu() {
    // Se relee en cada apertura y no una vez al cargar: el menú se colapsa, se
    // expande y marca su renglón activo, y basta con que una pantalla futura lo
    // dibuje después para que una lectura única quede corta.
    return Array.prototype.map
      .call(document.querySelectorAll('#sidebar a[href]'), function (link) {
        return {
          label: link.textContent.replace(/\s+/g, ' ').trim(),
          href: link.getAttribute('href'),
        };
      })
      .filter(function (entry) {
        return entry.label && entry.href;
      });
  }

  function matches(entry, query) {
    if (!query) return true;
    // Sin acentos y sin caja: quien escribe rápido pone "aeronave" y no
    // "Aeronaves", y en un teclado de teléfono los acentos cuestan un toque más.
    return fold(entry.label).indexOf(fold(query)) !== -1;
  }

  function fold(text) {
    // `normalize` existe en todo navegador que corra esta aplicación; el
    // `try` es por si un motor viejo no lo trae, y ahí simplemente se compara
    // con acentos en vez de romper la búsqueda entera.
    try {
      return text
        .toLocaleLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '');
    } catch (error) {
      return text.toLowerCase();
    }
  }

  function render(query) {
    var found = entries.filter(function (entry) {
      return matches(entry, query);
    });
    results.textContent = '';
    active = 0;

    if (query) {
      // La búsqueda global va **primero y siempre**, incluso cuando ningún
      // destino coincide: escribir la matrícula de una aeronave no tiene por qué
      // parecerse al nombre de una pantalla, y ése es justo el caso en que la
      // paleta tiene que servir de algo.
      found.unshift({
        label: palette.dataset.searchLabel + ' «' + query + '»',
        href: palette.dataset.searchUrl + '?q=' + encodeURIComponent(query),
        search: true,
      });
    }

    if (!found.length) {
      var empty = document.createElement('li');
      empty.className = 'command-palette-empty';
      empty.textContent = palette.dataset.emptyLabel || '';
      results.appendChild(empty);
      return;
    }

    found.forEach(function (entry) {
      var item = document.createElement('li');
      var link = document.createElement('a');
      link.href = entry.href;
      link.className = 'command-palette-item';
      link.setAttribute('role', 'option');
      if (entry.search) link.classList.add('is-search');
      // `textContent` y no `innerHTML`: `query` viene de lo que la persona
      // tecleó y termina dentro del rótulo de la primera opción.
      link.textContent = entry.label;
      item.appendChild(link);
      results.appendChild(item);
    });
    // Después de dibujarlas todas, no dentro del bucle: `select` mira la lista
    // viva, así que llamarlo en la primera vuelta marcaría la única que existe
    // en ese momento y dejaría al resto sin `aria-selected`.
    select(0);
  }

  function items() {
    return results.querySelectorAll('.command-palette-item');
  }

  function select(index) {
    var all = items();
    if (!all.length) return;
    active = (index + all.length) % all.length;
    Array.prototype.forEach.call(all, function (item, position) {
      var current = position === active;
      item.classList.toggle('is-active', current);
      item.setAttribute('aria-selected', current ? 'true' : 'false');
      if (current) item.scrollIntoView({ block: 'nearest' });
    });
  }

  function open() {
    // Se recuerda de dónde se abrió para devolver el foco al cerrar, igual que
    // hace el cuadro genérico: sin eso el foco vuelve al principio del documento
    // y quien navega por teclado pierde el sitio.
    opener = document.activeElement;
    entries = readMenu();
    palette.hidden = false;
    document.body.classList.add('palette-open');
    input.value = '';
    render('');
    input.focus();
  }

  function close() {
    palette.hidden = true;
    document.body.classList.remove('palette-open');
    if (opener && opener.focus) opener.focus();
  }

  document.addEventListener('keydown', function (event) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if (palette.hidden) open();
      else close();
      return;
    }
    if (palette.hidden) return;
    if (event.key === 'Escape') {
      // ⚠️ `app.js` también cierra la barra lateral con `Escape` en el mismo
      // `document`, así que un `Esc` en la paleta cerraba las dos cosas. No se
      // arregla desde acá: entre dos oyentes del **mismo** elemento,
      // `stopPropagation` no hace nada y `stopImmediatePropagation` sólo alcanza
      // a los registrados después, o sea que dependería del orden de las
      // etiquetas `<script>`. `app.js` pregunta si la paleta está abierta.
      close();
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      select(active + 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      select(active - 1);
    } else if (event.key === 'Enter') {
      var chosen = items()[active];
      if (chosen) {
        event.preventDefault();
        chosen.click();
      }
    }
  });

  input.addEventListener('input', function () {
    render(input.value.trim());
  });

  var trigger = document.getElementById('palette-open');
  if (trigger) trigger.addEventListener('click', open);

  palette.addEventListener('click', function (event) {
    if (event.target.closest('[data-palette-close]')) close();
  });

  // El puntero marca lo mismo que las flechas: si no, mover el ratón sobre la
  // lista y apretar Enter abre otra cosa que la resaltada.
  results.addEventListener('mousemove', function (event) {
    var item = event.target.closest('.command-palette-item');
    if (!item) return;
    select(Array.prototype.indexOf.call(items(), item));
  });
})();
