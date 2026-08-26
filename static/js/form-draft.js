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
      saved.hidden = false;
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
      if (notice) notice.hidden = true;
    }

    var draft = stored();
    if (draft && draft.values && notice) {
      var when = panel.querySelector('[data-form-draft-when]');
      if (when && draft.at) {
        when.textContent = new Date(draft.at).toLocaleString();
      }
      notice.hidden = false;
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
          if (notice) notice.hidden = true;
        } catch (error) {
          show(save.dataset.failedLabel || '');
        }
        return;
      }
      if (event.target.closest('[data-form-draft-restore]')) {
        var current = stored();
        if (current && current.values) restore(form, current.values);
        if (notice) notice.hidden = true;
        return;
      }
      if (event.target.closest('[data-form-draft-discard]')) drop();
    });

    // Guardado de verdad: el borrador ya cumplió y dejarlo ahí ofrecería
    // recuperar una versión vieja del registro que se acaba de crear.
    form.addEventListener('submit', drop);
  }

  function init() {
    document.querySelectorAll('[data-form-draft]').forEach(setUp);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
