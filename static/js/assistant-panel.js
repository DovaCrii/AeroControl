/* LV-332: panel lateral del asistente. Archivo propio por la CSP (sin JS embebido).
   El historial vive sólo en el DOM: recargar lo borra y nada se guarda en el navegador.
   La respuesta llega como un fragmento que el SERVIDOR ya escapó y armó; acá no se interpreta
   texto del modelo como HTML. Los textos de la pregunta se escriben con textContent. */
(function () {
  'use strict';
  var panel = document.getElementById('assistant-panel');
  if (!panel || !window.bootstrap) return;
  var form = document.getElementById('assistant-form');
  var input = document.getElementById('assistant-input');
  var send = document.getElementById('assistant-send');
  var log = document.getElementById('assistant-log');
  var suggest = document.getElementById('assistant-suggest');
  var busy = false;

  function instance() { return window.bootstrap.Offcanvas.getOrCreateInstance(panel); }

  // Ctrl+J abre o cierra (Ctrl+K es la paleta de comandos).
  document.addEventListener('keydown', function (event) {
    if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey &&
        event.key.toLowerCase() === 'j') {
      event.preventDefault();
      instance().toggle();
    }
  });

  panel.addEventListener('shown.bs.offcanvas', function () { input.focus(); });

  function bubble(cls, text) {
    var el = document.createElement('div');
    el.className = 'ai-msg ' + cls;
    el.textContent = text;
    log.appendChild(el);
    return el;
  }

  function skeleton() {
    var el = document.createElement('div');
    el.className = 'ai-msg ai-msg--bot ai-thinking';
    el.setAttribute('role', 'status');
    ['ai-bar', 'ai-bar ai-bar--short'].forEach(function (cls) {
      var bar = document.createElement('span');
      bar.className = cls;
      el.appendChild(bar);
    });
    var label = document.createElement('span');
    label.className = 'visually-hidden';
    label.textContent = panel.dataset.thinking;
    el.appendChild(label);
    return el;
  }

  function ask(question) {
    question = question.trim();
    if (busy || !question) return;
    busy = true;
    send.disabled = true;
    if (suggest) suggest.hidden = true;
    bubble('ai-msg--user', question);
    var waiting = skeleton();
    log.appendChild(waiting);
    log.scrollTop = log.scrollHeight;

    var body = new FormData(form);
    body.set('question', question);
    fetch(panel.dataset.url, {
      method: 'POST',
      body: body,
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }).then(function (response) {
      if (!response.ok) throw new Error('http-' + response.status);
      return response.text();
    }).then(function (html) {
      // Fragmento del servidor (ya escapado); sustituye al esqueleto.
      waiting.outerHTML = html;
    }).catch(function () {
      waiting.parentNode.removeChild(waiting);
      bubble('ai-msg--error', panel.dataset.failed);
    }).then(function () {
      busy = false;
      send.disabled = false;
      input.value = '';
      log.scrollTop = log.scrollHeight;
      input.focus();
    });
  }

  // `LV-346`: voto y copia, por delegación (los fragmentos llegan después de cargar la página).
  // El voto sólo envía el token firmado y +1/-1: nunca texto. Copiar usa `textContent`, que ya es
  // el texto escapado por el servidor.
  function say(actions, text) {
    var status = actions.querySelector('.ai-actions-status');
    if (status) status.textContent = text;
  }

  function vote(button) {
    var actions = button.closest('.ai-actions');
    if (!actions || actions.dataset.voting) return;
    actions.dataset.voting = '1';
    var body = new FormData();
    body.set('csrfmiddlewaretoken', form.querySelector('[name=csrfmiddlewaretoken]').value);
    body.set('usage_id', actions.dataset.usageId);
    body.set('vote', button.dataset.assistantVote);
    fetch(panel.dataset.voteUrl, {
      method: 'POST',
      body: body,
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }).then(function (response) {
      if (!response.ok) throw new Error('http-' + response.status);
      actions.querySelectorAll('[data-assistant-vote]').forEach(function (other) {
        other.setAttribute('aria-pressed', other === button ? 'true' : 'false');
        other.classList.toggle('active', other === button);
      });
      say(actions, panel.dataset.voteThanks);
    }).catch(function () {
      say(actions, panel.dataset.voteFailed);
    }).then(function () {
      delete actions.dataset.voting;
    });
  }

  function copy(button) {
    var actions = button.closest('.ai-actions');
    var message = button.closest('.ai-msg');
    var text = message && message.querySelector('.ai-msg-text');
    if (!actions || !text) return;
    var done = function () { say(actions, panel.dataset.copied); };
    var failed = function () { say(actions, panel.dataset.copyFailed); };
    if (!navigator.clipboard || !navigator.clipboard.writeText) return failed();
    navigator.clipboard.writeText(text.textContent).then(done, failed);
  }

  log.addEventListener('click', function (event) {
    var target = event.target.closest('[data-assistant-vote], [data-assistant-copy]');
    if (!target) return;
    if (target.hasAttribute('data-assistant-vote')) vote(target); else copy(target);
  });

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    ask(input.value);
  });

  input.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      ask(input.value);
    }
  });

  panel.querySelectorAll('[data-assistant-suggest]').forEach(function (button) {
    button.addEventListener('click', function () { ask(button.textContent.trim()); });
  });
})();
