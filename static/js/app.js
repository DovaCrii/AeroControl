// Base layout behaviour: theme toggle, sidebar, and generic modal wiring.
// Extracted from an inline <script> in base.html so the page carries no inline
// JavaScript and the CSP needs no 'unsafe-inline' for scripts (MASTER_PLAN
// V.10). Loads at the end of <body>, after the Bootstrap bundle (uses the
// `bootstrap` global). Translatable labels ride on the buttons' data-* set by
// the template; the htmx CSRF header comes from the body's hx-headers
// attribute, so no token is needed here.
(function () {
  var modalTrigger = null;

  // LV-208: `localStorage` **lanza** —no devuelve null— en una ventana privada o
  // con el almacenamiento de sitio bloqueado. Encontrado escribiendo el tirador
  // del ancho, que sí llevaba su `try/catch`. En este archivo **dos de los
  // cuatro accesos ya estaban protegidos** —los de `nav-groups-collapsed`, con
  // su comentario y todo— y los otros dos no, que es la forma en que este tipo
  // de defecto sobrevive: el patrón correcto está a la vista unas líneas más
  // abajo. Una excepción acá no deja un ajuste sin recordar, **corta la función
  // entera**. En `applyTheme` habría dejado el tema
  // aplicado a medias (los atributos ya escritos, el botón sin actualizar); en
  // `setSidebarCollapsed`, el `classList.toggle` ya ejecutado y el botón sin
  // rotular — o sea, el menú colapsado y su botón diciendo lo contrario.
  //
  // Envolver sólo el acceso y no el cuerpo: si no se puede guardar, la
  // preferencia vale para esta visita, que es mucho mejor que no funcionar.
  function remember(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (error) {
      /* sin almacenamiento la preferencia no sobrevive a la recarga */
    }
  }

  function recall(key) {
    try {
      return localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function applyTheme(theme) {
    var html = document.documentElement;
    html.setAttribute('data-theme', theme);
    html.setAttribute('data-bs-theme', theme);
    remember('theme', theme);
    var toggle = document.getElementById('theme-toggle');
    if (toggle) {
      toggle.setAttribute('aria-pressed', String(theme === 'dark'));
      var label = theme === 'dark' ? toggle.dataset.labelLight : toggle.dataset.labelDark;
      if (label) {
        toggle.setAttribute('title', label);
        toggle.setAttribute('aria-label', label);
      }
    }
    document.dispatchEvent(new CustomEvent('aero:themechange', { detail: { theme: theme } }));
  }
  function toggleTheme() {
    applyTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
  }
  function setSidebar(open) {
    var sidebar = document.getElementById('sidebar');
    var toggle = document.getElementById('sidebar-toggle');
    sidebar.classList.toggle('is-open', open);
    if (toggle && window.innerWidth < 769) toggle.setAttribute('aria-expanded', String(open));
  }
  function setSidebarCollapsed(collapsed) {
    var sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    sidebar.classList.toggle('is-collapsed', collapsed);
    remember('sidebar-collapsed', String(collapsed));
    var toggle = document.getElementById('sidebar-toggle');
    var innerToggle = document.getElementById('sidebar-collapse');
    if (toggle && window.innerWidth >= 769) toggle.setAttribute('aria-expanded', String(!collapsed));
    if (innerToggle) {
      var label = collapsed ? innerToggle.dataset.labelExpand : innerToggle.dataset.labelCollapse;
      if (label) {
        innerToggle.setAttribute('aria-label', label);
        innerToggle.setAttribute('title', label);
      }
    }
  }

  // LV-170: los grupos del menú se pliegan y **recuerdan** su estado, uno por
  // uno. Va en `localStorage` y no en la sesión del servidor a propósito: es una
  // preferencia de esta persona en este navegador, no un dato de la cuenta, y
  // guardarla en el servidor costaría una petición por click.
  //
  // Se guarda **sólo lo plegado**, no lo abierto. Así un grupo nuevo aparece
  // abierto sin que nadie tenga que migrar nada: lo que no está en la lista, se
  // ve. Al revés —guardar los abiertos— el grupo que se agregue mañana nacería
  // invisible para todos los que ya usaron el menú, que es la clase de estreno
  // que nadie descubre.
  function collapsedGroups() {
    try {
      var raw = localStorage.getItem('nav-groups-collapsed');
      return raw ? JSON.parse(raw) : [];
    } catch (error) {
      return [];  // localStorage bloqueado o JSON viejo: el menú abre entero.
    }
  }
  function setGroup(toggle, expanded) {
    var items = document.getElementById(toggle.getAttribute('aria-controls'));
    toggle.setAttribute('aria-expanded', String(expanded));
    if (items) items.hidden = !expanded;
  }
  var navToggles = document.querySelectorAll('.nav-group-toggle');
  if (navToggles.length) {
    var collapsed = collapsedGroups();
    navToggles.forEach(function (toggle) {
      setGroup(toggle, collapsed.indexOf(toggle.dataset.navGroup) === -1);
      toggle.addEventListener('click', function () {
        var expanded = toggle.getAttribute('aria-expanded') === 'true';
        setGroup(toggle, !expanded);
        var names = collapsedGroups().filter(function (name) {
          return name !== toggle.dataset.navGroup;
        });
        if (expanded) names.push(toggle.dataset.navGroup);
        try {
          localStorage.setItem('nav-groups-collapsed', JSON.stringify(names));
        } catch (error) {
          /* Sin poder guardar, el plegado sigue andando en esta página. */
        }
      });
    });
    // El grupo que contiene la página actual se abre aunque estuviera plegado:
    // si no, la pantalla en la que estás parado no aparece en el menú y el menú
    // pasa a contradecir a la página.
    var active = document.querySelector('.nav-group-items .nav-item.active');
    if (active) {
      var owner = active.closest('.nav-group').querySelector('.nav-group-toggle');
      if (owner) setGroup(owner, true);
    }
  }

  var themeToggle = document.getElementById('theme-toggle');
  if (themeToggle) themeToggle.addEventListener('click', toggleTheme);
  // Selects that submit their form on change (former inline onchange handlers).
  document.querySelectorAll('[data-autosubmit]').forEach(function (select) {
    select.addEventListener('change', function () { this.form.submit(); });
  });

  document.getElementById('sidebar-toggle').addEventListener('click', function () {
    if (window.innerWidth >= 769) {
      setSidebarCollapsed(!document.getElementById('sidebar').classList.contains('is-collapsed'));
    } else {
      setSidebar(!document.getElementById('sidebar').classList.contains('is-open'));
    }
  });
  document.getElementById('sidebar-collapse').addEventListener('click', function () {
    setSidebarCollapsed(!document.getElementById('sidebar').classList.contains('is-collapsed'));
  });
  applyTheme(document.documentElement.getAttribute('data-theme') || 'light');
  if (window.innerWidth >= 769 && recall('sidebar-collapsed') === 'true') setSidebarCollapsed(true);
  document.querySelectorAll('#sidebar a').forEach(function (link) {
    link.title = link.textContent.replace(/\s+/g, ' ').trim();
    link.addEventListener('click', function () { setSidebar(false); });
  });
  document.addEventListener('keydown', function (event) { if (event.key === 'Escape') { setSidebar(false); } });
  document.body.addEventListener('click', function (event) {
    var trigger = event.target.closest('[data-bs-target="#generic-modal"]');
    if (trigger) { modalTrigger = trigger; }
  });
  // LV-108: htmx does not swap error responses -- by default only 2xx replaces
  // anything. This app answers an invalid modal form with **422 plus the
  // re-rendered form** (HtmxFormMixin.form_invalid, AlertResolve,
  // FlightPermissionCorrectStatus), so without this the server said exactly
  // what was wrong and the screen showed nothing at all: the person clicks
  // "Save" and the modal just sits there. Verified in the browser, both ways.
  // Only 422, which is this app's "your input is invalid, here is the form
  // again" -- a 500 is not a form and must not be swapped into the page.
  document.body.addEventListener('htmx:beforeSwap', function (event) {
    if (event.detail.xhr && event.detail.xhr.status === 422) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });
  document.body.addEventListener('htmx:afterSwap', function (event) {
    if (event.detail.target.id !== 'modal-content') return;
    var modal = document.getElementById('generic-modal');
    // LV-92: a PDF viewer inside the default dialog is a letterbox. Decided
    // from what was actually swapped in, rather than by having each template
    // declare its own width -- a flag the fragments had to remember to set
    // would be wrong the first time somebody forgot it, and wrong silently.
    var dialog = modal.querySelector('.modal-dialog');
    var showsDocument = !!modal.querySelector(
      '.document-preview, .document-preview-image'
    );
    dialog.classList.toggle('modal-xl', showsDocument);
    dialog.classList.toggle('modal-lg', !showsDocument);
    bootstrap.Modal.getOrCreateInstance(modal).show();
    // LV-34: apply the responsible-type toggle to a form just loaded into the modal.
    if (window.initResponsibleType) window.initResponsibleType();
    // A validation re-render swaps the content of an already-open modal, so
    // shown.bs.modal never fires again: the errors appeared with no focus and
    // no announcement. Focus the first invalid field when there is one.
    window.setTimeout(function () {
      var invalid = modal.querySelector('.is-invalid, [aria-invalid="true"]');
      if (invalid) invalid.focus();
    }, 50);
  });
  document.getElementById('generic-modal').addEventListener('shown.bs.modal', function () {
    var modal = this;
    window.setTimeout(function () {
      var first = modal.querySelector('input, select, textarea, button:not(.btn-close)');
      if (first) first.focus();
    }, 50);
  });
  document.getElementById('generic-modal').addEventListener('hidden.bs.modal', function () {
    if (modalTrigger) { modalTrigger.focus(); }
  });
  document.body.addEventListener('modal-form-success', function () {
    bootstrap.Modal.getOrCreateInstance(document.getElementById('generic-modal')).hide();
    window.location.reload();
  });

  // Progressive enhancement for former inline JS (V.10 CSP: no inline handlers,
  // no javascript: URLs).
  // <form data-confirm="…"> asks before submitting; declining cancels it.
  document.body.addEventListener('submit', function (event) {
    var form = event.target.closest('form[data-confirm]');
    if (form && !window.confirm(form.dataset.confirm)) event.preventDefault();
  });
  // <a data-history-back href="/fallback/"> goes back when there is history,
  // otherwise follows its real href (which works with CSP and no history).
  document.body.addEventListener('click', function (event) {
    var back = event.target.closest('[data-history-back]');
    if (back && window.history.length > 1) {
      event.preventDefault();
      window.history.back();
    }
  });
  // LV-5: <form data-loading-label="…"> shows a busy state on submit (button
  // disabled + label swap + an indeterminate progress bar) for requests with
  // no client-visible progress of their own (e.g. server-side KMZ parsing),
  // so a slow response does not look hung. The native submission still
  // proceeds and reloads the page normally; without JavaScript the form still
  // works, it just shows no feedback while it waits.
  document.body.addEventListener('submit', function (event) {
    var form = event.target.closest('form[data-loading-label]');
    if (!form) return;
    var button = form.querySelector('button[type="submit"]');
    if (button) {
      button.disabled = true;
      button.textContent = form.dataset.loadingLabel;
    }
    var progress = form.querySelector('[data-loading-progress]');
    if (progress) progress.classList.remove('d-none');
  });

  // LV-40: open the tab named by the URL hash (#tab-…). A redirect that lands on
  // a detail page with a hash (e.g. after uploading a document from a fiche,
  // which returns to costcenter-detail#tab-documents) then shows the right tab
  // instead of the default Summary one. Harmless when the tab is absent.
  var tabHash = window.location.hash;
  if (tabHash && /^#tab-[\w-]+$/.test(tabHash) && window.bootstrap && bootstrap.Tab) {
    var tabTrigger = document.querySelector(
      '[data-bs-toggle="tab"][data-bs-target="' + tabHash + '"]'
    );
    if (tabTrigger) bootstrap.Tab.getOrCreateInstance(tabTrigger).show();
  }

  // LV-34/LV-56: the cost-center "responsible type" picker shows only the
  // *extra* field its choice needs (operator / external contact) on top of
  // the contract administrator name, which is always required and always
  // visible -- not part of this toggle. Delegated so it works on the full
  // page and inside the HTMX modal alike.
  function applyResponsibleType(select) {
    var groups = {
      administrator: [],
      operator: ['div_id_responsible_operator'],
      external: ['div_id_responsible_contact_name', 'div_id_responsible_contact_email'],
    };
    var all = [
      'div_id_responsible_operator',
      'div_id_responsible_contact_name',
      'div_id_responsible_contact_email',
    ];
    var show = groups[select.value] || [];
    all.forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.style.display = show.indexOf(id) >= 0 ? '' : 'none';
    });
  }
  window.initResponsibleType = function () {
    var select = document.getElementById('id_responsible_type');
    if (select) applyResponsibleType(select);
  };
  document.body.addEventListener('change', function (event) {
    if (event.target && event.target.id === 'id_responsible_type') {
      applyResponsibleType(event.target);
    }
  });
  window.initResponsibleType();
})();

/* Formularios que preguntan antes de enviar (`R5`).
 *
 * `<form data-confirm="…">` y no `onsubmit="…"`: la política de seguridad de
 * contenido de esta aplicación no lleva `unsafe-inline` en `script-src`, así
 * que un manejador escrito en el atributo **no se ejecuta en producción** — el
 * formulario se enviaría sin preguntar y la pantalla parecería tener una
 * confirmación que no tiene. Peor que no tenerla.
 *
 * Delegado en `document` y no enganchado a cada formulario: los que llegan por
 * htmx después de la carga quedan cubiertos sin volver a inicializar nada.
 */
(function () {
  'use strict';
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form || !form.dataset || !form.dataset.confirm) return;
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
})();
