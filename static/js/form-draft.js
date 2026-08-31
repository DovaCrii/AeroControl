// LV-154: guardar lo tipeado sin guardar el registro.
//
// Pedido textual: *"deja un botón de dejar en borrador, por si toca salir y
// avanzar en otros temas, para no perder lo llenado"*. El formulario del permiso
// es el más largo de la app y hoy es todo o nada: sin centro de costo, propósito
// y tipo de área no guarda, y esas tres columnas son obligatorias en la base.
//
// **El borrador vive en este navegador**, decisión del usuario. Un borrador de
// verdad —una fila incompleta en la base— habría exigido hacer nulas esas tres
// columnas con su migración, y decidir qué hacen con un permiso sin faena el
// panel, las alertas, el calendario y el informe, que hoy asumen que la tiene.
//
// Sin texto en este archivo: los rótulos vienen traducidos por el servidor en
// `data-*`. Sin JS inline: la CSP es `script-src 'self'`.
(function () {
  'use strict';

  var STORE_PREFIX = 'aerocontrol:draft:';

  function storage() {
    // Una ventana privada, o un navegador con el almacenamiento bloqueado, hace
    // que `localStorage` lance al tocarlo. El formulario tiene que seguir
    // funcionando: sin almacenamiento simplemente no hay borrador.
    try {
      var probe = '__aerocontrol__';
      window.localStorage.setItem(probe, '1');
      window.localStorage.removeItem(probe);
      return window.localStorage;
    } catch (error) {
      return null;
    }
  }

  // LV-209: **`hidden` no oculta un elemento con `d-flex`**, y por eso el botón
  // "Descartarlo" parecía no hacer nada.
  //
  // El borrador **sí** se borraba de `localStorage`; lo que no se iba era el
  // aviso, así que en pantalla no pasaba nada. La causa está en el bundle de
  // Bootstrap y se puede medir: `[hidden]{display:none!important}` vive en la
  // posición ~10.129 y `.d-flex{display:flex!important}` en la ~163.993. Los dos
  // selectores tienen la misma especificidad (un atributo y una clase valen
  // igual) y los dos son `!important`, así que **gana el que viene después** —
  // `d-flex`. El atributo se aplicaba y no servía de nada.
  //
  // `d-none` (~164.069) está **después** de `d-flex`, así que ésa sí gana: es la
  // única de las tres que puede ocultar este elemento. Se pone junto al atributo
  // y no en su lugar, porque `hidden` es lo que leen los lectores de pantalla.
  function setHidden(element, value) {
    if (!element) return;
    element.hidden = value;
    element.classList.toggle('d-none', value);
  }

  function fields(form) {
    return Array.prototype.filter.call(
      form.querySelectorAll('input, select, textarea'),
      function (field) {
        // El token CSRF es de esta sesión y de este formulario: guardarlo sería
        // guardar una credencial y restaurarlo, restaurar una vencida.
        return (
          field.name &&
          field.name !== 'csrfmiddlewaretoken' &&
          field.type !== 'file' &&
          field.type !== 'password'
        );
      }
    );
  }

  function collect(form) {
    var values = {};
    fields(form).forEach(function (field) {
      if (field.type === 'checkbox' || field.type === 'radio') {
        if (!field.checked) return;
        (values[field.name] = values[field.name] || []).push(field.value);
      } else if (field.multiple) {
        values[field.name] = Array.prototype.map.call(
          field.selectedOptions,
          function (option) {
            return option.value;
          }
        );
      } else if (field.value) {
        values[field.name] = field.value;
      }
    });
    return values;
  }

  function restore(form, values) {
    fields(form).forEach(function (field) {
      var saved = values[field.name];
      if (saved === undefined) {
        if (field.type === 'checkbox' || field.type === 'radio') {
          field.checked = false;
        }
        return;
      }
      if (field.type === 'checkbox' || field.type === 'radio') {
        field.checked = saved.indexOf(field.value) !== -1;
      } else if (field.multiple) {
        Array.prototype.forEach.call(field.options, function (option) {
          option.selected = saved.indexOf(option.value) !== -1;
        });
      } else {
        field.value = saved;
      }
      // Los rosters escuchan `change` para recontar lo elegido (LV-151).
      field.dispatchEvent(new Event('change', { bubbles: true }));
    });
  }

  function setUp(panel) {
    var store = storage();
    if (!store) return;
    var form = panel.closest('form');
    if (!form) return;
    var key = STORE_PREFIX + (panel.dataset.formDraftKey || window.location.pathname);
    var notice = panel.querySelector('[data-form-draft-notice]');
    var saved = panel.querySelector('[data-form-draft-saved]');

    function show(message) {
      if (!saved) return;
      saved.textContent = message;
      setHidden(saved, false);
    }

    function stored() {
      try {
        return JSON.parse(store.getItem(key));
      } catch (error) {
        return null;
      }
    }

    function drop() {
      try {
        store.removeItem(key);
      } catch (error) {
        /* nada que hacer: el borrador ya no se puede borrar ni leer */
      }
      setHidden(notice, true);
    }

    var draft = stored();
    if (draft && draft.values && notice) {
      // LV-198: la fecha y **sus paréntesis** aparecen juntos o no aparecen. El
      // envoltorio estaba fuera del span, así que un borrador sin `at` dejaba a
      // la vista un "()" que se lee como pantalla rota.
      var when = panel.querySelector('[data-form-draft-when]');
      var wrap = panel.querySelector('[data-form-draft-when-wrap]');
      if (when && draft.at) {
        when.textContent = new Date(draft.at).toLocaleString();
        setHidden(wrap, false);
      }
      setHidden(notice, false);
    } else {
      // LV-210: y sin borrador se apaga explícitamente, por lo mismo que el
      // índice: el `hidden` del HTML no basta contra `d-flex`, así que el aviso
      // se veía en un formulario en blanco.
      setHidden(notice, true);
    }

    // El listener va en el **formulario**, no en el panel: el botón "Guardar
    // borrador" vive junto a "Guardar", o sea fuera del panel del aviso.
    // Escuchando sólo el panel, el clic nunca llegaba -- encontrado en el
    // navegador, no por un test: el DOM estaba entero y no pasaba nada.
    form.addEventListener('click', function (event) {
      var save = event.target.closest('[data-form-draft-save]');
      if (save) {
        try {
          store.setItem(
            key,
            JSON.stringify({ at: Date.now(), values: collect(form) })
          );
          show(save.dataset.savedLabel || '');
          setHidden(notice, true);
        } catch (error) {
          show(save.dataset.failedLabel || '');
        }
        return;
      }
      if (event.target.closest('[data-form-draft-restore]')) {
        var current = stored();
        if (current && current.values) restore(form, current.values);
        setHidden(notice, true);
        return;
      }
      if (event.target.closest('[data-form-draft-discard]')) drop();
    });

    // Guardado de verdad: el borrador ya cumplió y dejarlo ahí ofrecería
    // recuperar una versión vieja del registro que se acaba de crear.
    form.addEventListener('submit', drop);
  }

  // LV-198: el índice de borradores, para que existan **fuera del formulario**.
  //
  // Pedido del usuario: *"el borrador no quedar abajo, si no generar un listado
  // fuera que existen borradores"*. El aviso vivía al pie del formulario de alta,
  // así que sólo se descubría volviendo a esa misma pantalla — y un borrador que
  // hay que recordar para encontrarlo no cumple el pedido que lo creó (`LV-154`:
  // "por si toca salir y avanzar en otros temas").
  //
  // **Es por navegador, y no puede ser de otra forma**: el borrador vive en
  // `localStorage` por la decisión de `LV-154`, que está escrita arriba con su
  // razón — una fila incompleta en la base habría exigido hacer nulas tres
  // columnas obligatorias y decidir qué hacen con un permiso sin faena el panel,
  // las alertas, el calendario y el informe. Un índice compartido entre personas
  // es esa otra decisión, no esta fila.
  //
  // Vive en **este** archivo y no en uno propio a propósito: comparte
  // `STORE_PREFIX` y `storage()` con quien los escribe. Con el prefijo duplicado
  // en dos archivos, el día que cambie el índice deja de encontrar los
  // borradores — y lo haría en silencio, que es la peor forma.
  function setUpIndex(box) {
    var store = storage();
    if (!store) return;
    var found = [];
    try {
      for (var index = 0; index < store.length; index += 1) {
        var key = store.key(index);
        if (key && key.indexOf(STORE_PREFIX) === 0) found.push(key);
      }
    } catch (error) {
      return;
    }
    // LV-210: se oculta **explícitamente** cuando no hay ninguno, en vez de
    // volver temprano confiando en el estado del HTML. Volver temprano fue el
    // defecto: la caja arrancaba visible por el `d-flex` y nadie la apagaba. Con
    // esta línea, el JS es la única autoridad sobre su visibilidad y no importa
    // con qué clases llegue.
    if (!found.length) {
      setHidden(box, true);
      return;
    }
    var count = box.querySelector('[data-draft-index-count]');
    if (count) {
      var template =
        found.length === 1 ? box.dataset.oneLabel : box.dataset.manyLabel;
      count.textContent = (template || '').replace('%(count)s', found.length);
    }
    setHidden(box, false);
  }

  function init() {
    document.querySelectorAll('[data-form-draft]').forEach(setUp);
    document.querySelectorAll('[data-draft-index]').forEach(setUpIndex);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
