// Base layout behaviour: theme toggle, sidebar, and generic modal wiring.
// Extracted from an inline <script> in base.html so the page carries no inline
// JavaScript and the CSP needs no 'unsafe-inline' for scripts (MASTER_PLAN
// V.10). Loads at the end of <body>, after the Bootstrap bundle (uses the
// `bootstrap` global). Translatable labels ride on the buttons' data-* set by
// the template; the htmx CSRF header comes from the body's hx-headers
// attribute, so no token is needed here.
(function () {
  var modalTrigger = null;

  function applyTheme(theme) {
    var html = document.documentElement;
    html.setAttribute('data-theme', theme);
    html.setAttribute('data-bs-theme', theme);
    localStorage.setItem('theme', theme);
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
    localStorage.setItem('sidebar-collapsed', String(collapsed));
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
  if (window.innerWidth >= 769 && localStorage.getItem('sidebar-collapsed') === 'true') setSidebarCollapsed(true);
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
