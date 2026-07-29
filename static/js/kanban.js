// Kanban drag-and-drop (SortableJS + htmx). Extracted from an inline <script>
// in kanban.html so the page carries no inline JavaScript (MASTER_PLAN V.10).
// The two move-error messages ride on the #kanban-move-error banner's data-*
// attributes set by the template. Loads at the end of <body>, after the
// SortableJS vendor bundle and htmx.
(function () {
  function initSortables() {
    var params = new URLSearchParams(window.location.search);
    if (params.get('operator') || params.get('priority') || params.get('state') || params.get('label') || params.get('q')) return;
    var board = document.getElementById('kanban-board');
    if (!board) return;
    document.querySelectorAll('#kanban-board .kanban-column-body').forEach(function (el) {
      if (el._kanbanSortable) return;
      el._kanbanSortable = new Sortable(el, {
        group: 'kanban',
        animation: 150,
        ghostClass: 'kanban-ghost',
        chosenClass: 'sortable-chosen',
        onEnd: function (evt) {
          var taskId = evt.item.dataset.taskId;
          var stageId = evt.to.dataset.stageId;
          htmx.ajax('POST', '/workboard/tasks/' + taskId + '/move/', {
            values: { stage_id: stageId, new_order: evt.newIndex },
            source: document.body
          });
        }
      });
    });
  }

  function refreshBoard() {
    htmx.ajax('GET', '/workboard/_board/' + window.location.search,
      { target: '#kanban-board', swap: 'innerHTML' });
  }

  document.addEventListener('DOMContentLoaded', initSortables);
  document.body.addEventListener('htmx:afterSwap', function (event) {
    if (event.detail.target.id === 'kanban-board') initSortables();
  });
  // A rejected move (403/400) returns no HX-Trigger, so the board would keep
  // showing the card where it was dropped even though the server refused it.
  // Snap the board back to the truth and announce why.
  document.body.addEventListener('htmx:responseError', function (event) {
    var cfg = event.detail.requestConfig || {};
    if (!cfg.path || cfg.path.indexOf('/move/') === -1) return;
    var status = event.detail.xhr ? event.detail.xhr.status : 0;
    var banner = document.getElementById('kanban-move-error');
    if (banner) {
      banner.textContent = status === 403 ? banner.dataset.msgForbidden : banner.dataset.msgError;
      banner.classList.remove('d-none');
    }
    refreshBoard();
  });
  document.body.addEventListener('board-refresh', refreshBoard);
})();
