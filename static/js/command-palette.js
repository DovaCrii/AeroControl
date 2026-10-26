// `UX-25` · La paleta de comandos (`Ctrl/⌘+K`), y con ella la búsqueda móvil de
// `UX-24`. `LV-381` F4 le suma el grupo en cada rótulo, los «Recientes» y el
// cuadro de la barra superior como segunda puerta de entrada.
//
// Quien trabaja alertas entra veinte veces al día y hoy cada entrada cuesta
// abrir el menú, buscar el grupo y encontrar el renglón. Y bajo 768 px la
// búsqueda global desaparecía sin dejar nada en su lugar: en el teléfono, que es
// donde se trabaja en faena, la aplicación no tenía búsqueda.
//
// **Los destinos se leen del menú lateral, en el momento de abrir.** No es
// pereza: el menú ya esconde lo que esta persona no puede ver (`LV-381` F1: cada
// entrada del registro declara su permiso), así que la paleta hereda los permisos
// sin preguntarle nada al servidor, y no hay una segunda lista que se
// desincronice el día que alguien agregue una pantalla. Una lista propia habría
// terminado ofreciendo rutas que van a un 403 — que es `LV-130`, enseñar a
// desconfiar de la pantalla.
//
// **Recientes** (`LV-381` F4, D3): las últimas pantallas y fichas que esta persona
// abrió, en `localStorage` de este navegador. Sin migración y sin servidor: es una
// comodidad de quien mira, no un dato de la cuenta. Se guardan con el usuario que
// las visitó (en un equipo compartido, otra sesión no hereda los títulos de fichas
// ajenas) y se ignora todo lo que no sea una ruta relativa (el contenido de
// `localStorage` no es de fiar: un `javascript:` ahí no debe llegar a un enlace).
//
// Sin texto en este archivo: los rótulos llegan traducidos en `data-*`. Sin JS
// inline: la CSP es `script-src 'self'`.
(function () {
  'use strict';

  var palette = document.getElementById('command-palette');
  if (!palette) return;

  var input = document.getElementById('command-palette-input');
  var results = document.getElementById('command-palette-results');
  var box = document.querySelector('.global-search input[type="search"]');
  var RECENT_KEY = 'palette-recents';
  var RECENT_MAX = 8;
  var userId = palette.dataset.user || '';
  var opener = null;
  var entries = [];
  var active = 0;
  var restoringFocus = false;

  function clean(text) {
    return (text || '').replace(/\s+/g, ' ').trim();
  }

  function groupOf(link) {
    var group = link.closest('.nav-group');
    if (group) {
      var toggle = group.querySelector('.nav-group-toggle');
      return clean(toggle ? toggle.textContent : '');
    }
    var zone = link.closest('.nav-admin-zone');
    if (zone) {
      var label = zone.querySelector('.nav-admin-label');
      return clean(label ? label.textContent : '');
    }
    return '';  // el bloque de arriba (panel, bandeja, alertas) no tiene título
  }

  function readMenu() {
    // Se relee en cada apertura y no una vez al cargar: el menú se colapsa, se
    // expande y marca su renglón activo, y basta con que una pantalla futura lo
    // dibuje después para que una lectura única quede corta.
    //
    // El rótulo sale de `.nav-label` y no del texto del enlace: el enlace de las
    // alertas lleva además el contador, y «Alertas 3» no es el nombre de nada.
    // Los atajos del rol («Su jornada») repiten destinos que ya están en su
    // grupo: se leen al final y sólo cuentan si traen un destino que el menú no
    // tiene, así que nunca aparece el mismo renglón dos veces.
    var seen = {};
    var found = [];
    var links = Array.prototype.slice.call(document.querySelectorAll('#sidebar a[href]'));
    links.sort(function (a, b) {
      return Number(a.classList.contains('nav-shortcut')) - Number(b.classList.contains('nav-shortcut'));
    });
    links.forEach(function (link) {
      var node = link.querySelector('.nav-label');
      var label = clean(node ? node.textContent : '');
      var href = link.getAttribute('href');
      if (!label || !href || seen[href]) return;
      seen[href] = true;
      found.push({ label: label, href: href, group: groupOf(link), menu: true });
    });
    return found;
  }

  function matches(entry, query) {
    if (!query) return true;
    // Sin acentos y sin caja: quien escribe rápido pone "aeronave" y no
    // "Aeronaves", y en un teclado de teléfono los acentos cuestan un toque más.
    // Se busca también en el grupo: escribir "informes" lista los tres informes.
    return fold(entry.group + ' ' + entry.label).indexOf(fold(query)) !== -1;
  }

  function fold(text) {
    // `normalize` existe en todo navegador que corra esta aplicación; el
    // `try` es por si un motor viejo no lo trae, y ahí simplemente se compara
    // con acentos en vez de romper la búsqueda entera.
    try {
      return text
        .toLocaleLowerCase()
        .normalize('NFD')
        .replace(/[̀-ͯ]/g, '');
    } catch (error) {
      return text.toLowerCase();
    }
  }

  // --- Recientes -----------------------------------------------------------

  function isRelativePath(href) {
    return typeof href === 'string' && /^\/(?!\/)/.test(href);
  }

  function readRecents() {
    try {
      var data = JSON.parse(localStorage.getItem(RECENT_KEY));
      if (!data || data.user !== userId || !Array.isArray(data.items)) return [];
      return data.items.filter(function (item) {
        return item && isRelativePath(item.href) && typeof item.label === 'string';
      });
    } catch (error) {
      return [];  // bloqueado o JSON inválido: sin recientes, no una paleta rota
    }
  }

  function writeRecents(items) {
    try {
      localStorage.setItem(RECENT_KEY, JSON.stringify({ user: userId, items: items }));
    } catch (error) {
      /* Sin poder guardar, la paleta sigue andando sin recordar esta visita. */
    }
  }

  function currentPage() {
    // Una ficha se reconoce por sus migas (`LV-381` F3): el último eslabón es la
    // ficha y el anterior, su lista. Cualquier otra pantalla es un destino del
    // menú y se reconoce por el renglón que el servidor marcó como actual.
    var crumb = document.querySelector('nav.ac-breadcrumb .breadcrumb-item.active');
    if (crumb) {
      var trail = crumb.parentNode.querySelectorAll('.breadcrumb-item');
      return {
        href: location.pathname,
        label: clean(crumb.textContent),
        group: trail.length > 1 ? clean(trail[trail.length - 2].textContent) : '',
        menu: false,
      };
    }
    var link = document.querySelector('#sidebar a.nav-item[aria-current="page"]:not(.nav-shortcut)');
    var node = link && link.querySelector('.nav-label');
    var href = link && link.getAttribute('href');
    if (!node || !isRelativePath(href)) return null;
    return { href: href, label: clean(node.textContent), group: groupOf(link), menu: true };
  }

  function recordVisit() {
    var page = currentPage();
    if (!page || !page.label) return;
    var items = readRecents().filter(function (item) {
      return item.href !== page.href;
    });
    items.unshift(page);
    writeRecents(items.slice(0, RECENT_MAX));
  }

  function recents() {
    var known = {};
    entries.forEach(function (entry) {
      known[entry.href] = true;
    });
    return readRecents()
      .filter(function (item) {
        // La pantalla en la que ya estás no es un reciente; y un destino del
        // menú que el menú de ahora no ofrece (cambió el permiso) tampoco.
        if (item.href === location.pathname) return false;
        return !item.menu || known[item.href];
      })
      .slice(0, RECENT_MAX);
  }

  // --- Dibujo --------------------------------------------------------------

  function heading(text) {
    var item = document.createElement('li');
    item.className = 'command-palette-heading';
    item.setAttribute('role', 'presentation');
    item.textContent = text;
    return item;
  }

  function row(entry) {
    var item = document.createElement('li');
    var link = document.createElement('a');
    link.href = entry.href;
    link.className = 'command-palette-item';
    link.setAttribute('role', 'option');
    if (entry.search) link.classList.add('is-search');
    if (entry.group) {
      var group = document.createElement('span');
      group.className = 'command-palette-group';
      group.textContent = entry.group + ' › ';
      link.appendChild(group);
    }
    var label = document.createElement('span');
    // `textContent` y no `innerHTML`: `query` viene de lo que la persona
    // tecleó y termina dentro del rótulo de la primera opción, y los títulos de
    // los recientes vienen de `localStorage`.
    label.textContent = entry.label;
    link.appendChild(label);
    item.appendChild(link);
    return item;
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

    var recent = query ? [] : recents();
    if (recent.length) {
      results.appendChild(heading(palette.dataset.recentLabel || ''));
      recent.forEach(function (entry) {
        results.appendChild(row(entry));
      });
      results.appendChild(heading(palette.dataset.gotoLabel || ''));
    }
    found.forEach(function (entry) {
      results.appendChild(row(entry));
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
    if (opener && opener.focus) {
      // Si se abrió desde el cuadro de la barra, devolverle el foco volvería a
      // abrir la paleta (se abre al recibirlo): se marca que es una restitución.
      restoringFocus = true;
      opener.focus();
      restoringFocus = false;
    }
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

  // El cuadro «Buscar en AeroControl» de la barra es la puerta visible de la
  // paleta (`LV-381` F4, V7): al recibir el foco, o un clic si ya lo tenía,
  // abre la paleta. Y su pista `Ctrl K` dice `⌘ K` donde corresponde.
  if (box) {
    box.addEventListener('focus', function () {
      if (!restoringFocus && palette.hidden) open();
    });
    box.addEventListener('click', function () {
      if (palette.hidden) open();
    });
  }
  var hint = document.querySelector('.global-search-hint');
  var platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '';
  if (hint && /Mac|iPhone|iPad/i.test(platform)) hint.textContent = '⌘ K';

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

  recordVisit();
})();
