// LV-151: buscar dentro de un roster de casillas, y decir cuántas van elegidas.
//
// Sin JS inline (la CSP es `script-src 'self'`) y sin texto: los rótulos vienen
// traducidos por el servidor en `data-roster-count-label` /
// `data-roster-matches-label`, con `%(selected)s`, `%(total)s` y `%(matches)s`
// como marcadores.
//
// El filtro es del lado del navegador a propósito: las 41 opciones ya están en
// la página, así que escribir tres letras no debería costar una petición.
(function () {
  'use strict';

  // "Álvaro" tiene que encontrarse escribiendo "alvaro": se comparan las dos
  // puntas sin tildes. `normalize` está en todo navegador que corra esta app.
  function fold(text) {
    return (text || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  }

  // Los marcadores van entre llaves porque `makemessages` duplica los `%` de una
  // cadena de plantilla: `%(total)s` habría quedado como `%%(total)s` en el
  // catálogo y el rótulo saldría en inglés en la app en español.
  function format(template, values) {
    return Object.keys(values).reduce(function (text, key) {
      return text.replace('{' + key + '}', values[key]);
    }, template || '');
  }

  function setUp(roster) {
    var search = roster.querySelector('[data-roster-search]');
    var onlySelected = roster.querySelector('[data-roster-only-selected]');
    var counter = roster.querySelector('[data-roster-count]');
    var empty = roster.querySelector('[data-roster-empty]');
    var items = Array.prototype.slice.call(
      roster.querySelectorAll('[data-roster-item]')
    );
    if (!items.length) return;

    items.forEach(function (item) {
      item.dataset.rosterFold = fold(item.dataset.rosterText);
    });

    function apply() {
      var needle = fold(search ? search.value : '');
      var wantSelected = Boolean(onlySelected && onlySelected.checked);
      var shown = 0;
      var selected = 0;
      items.forEach(function (item) {
        var box = item.querySelector('input[type="checkbox"]');
        var isChecked = Boolean(box && box.checked);
        if (isChecked) selected += 1;
        var matches =
          (!needle || item.dataset.rosterFold.indexOf(needle) !== -1) &&
          (!wantSelected || isChecked);
        // Una casilla marcada que el filtro esconde seguiría enviándose, y eso
        // es correcto: filtrar es mirar, no des-elegir. Por eso el contador de
        // elegidas cuenta sobre **todas** las opciones, no sobre las visibles.
        item.hidden = !matches;
        if (matches) shown += 1;
      });
      if (empty) empty.hidden = shown !== 0;
      if (counter) {
        var showingAll = shown === items.length;
        counter.textContent = showingAll
          ? format(roster.dataset.rosterCountLabel, {
              selected: selected,
              total: items.length,
            })
          : format(roster.dataset.rosterCountLabel, {
              selected: selected,
              total: items.length,
            }) +
            ' · ' +
            format(roster.dataset.rosterMatchesLabel, {
              matches: shown,
              total: items.length,
            });
      }
    }

    if (search) search.addEventListener('input', apply);
    if (onlySelected) onlySelected.addEventListener('change', apply);
    roster.addEventListener('change', function (event) {
      if (event.target.matches('input[type="checkbox"][name]')) apply();
    });
    apply();
  }

  function init() {
    document.querySelectorAll('[data-roster]').forEach(setUp);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
