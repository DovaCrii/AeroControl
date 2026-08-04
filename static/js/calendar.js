// Calendar view (FullCalendar). Extracted from an inline <script> in
// core/calendar.html so the page carries no inline JavaScript (MASTER_PLAN
// V.10). Locale, the selected board and the button labels ride on #calendar-app
// data-* attributes set by the template. Loads at the end of <body>, after the
// FullCalendar vendor bundle.
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    var root = document.getElementById('calendar-app');
    // LV-47: one wrapper for the whole no-JS fallback (month title, nav, and
    // the plain table) so a single toggle hides all of it once FullCalendar
    // takes over -- previously only the table was hidden here, leaving its
    // header's prev/next always visible and disconnected from FullCalendar.
    var fallback = document.querySelector('.calendar-noscript');
    var filter = document.getElementById('calendar-type-filter');
    if (!root || !window.FullCalendar) return;
    var costCenter = document.getElementById('calendar-cost-center');
    var aircraft = document.getElementById('calendar-aircraft');
    var operator = document.getElementById('calendar-operator');
    var typeQuery = function () {
      return filter.value === 'all'
        ? 'permission,flight,assignment,maintenance,document,qualification,task'
        : filter.value;
    };
    var calendar = new FullCalendar.Calendar(root, {
      locale: root.dataset.locale || 'es', firstDay: 1, initialView: 'dayGridMonth',
      height: 'auto', expandRows: true, dayMaxEvents: 3,
      headerToolbar: { left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,listMonth' },
      buttonText: {
        today: root.dataset.textToday,
        month: root.dataset.textMonth,
        week: root.dataset.textWeek,
        list: root.dataset.textList,
      },
      events: function (info, success, failure) {
        var params = new URLSearchParams({
          start: info.startStr, end: info.endStr, types: typeQuery(),
          board: root.dataset.board || '',
          cost_center: costCenter.value, aircraft: aircraft.value, operator: operator.value,
        });
        fetch(root.dataset.eventsUrl + '?' + params.toString())
          .then(function (response) { if (!response.ok) throw new Error('Calendar request failed'); return response.json(); })
          .then(success).catch(failure);
      },
      eventClick: function (info) {
        if (info.event.url) { info.jsEvent.preventDefault(); window.location.assign(info.event.url); }
      },
      // Titles are kept short so they fit a month cell; the full label (with the
      // Kanban stage) stays reachable on hover.
      eventDidMount: function (info) {
        var full = info.event.extendedProps.tooltip || info.event.title;
        info.el.setAttribute('title', full);
      }
    });
    calendar.render(); fallback.hidden = true;
    filter.addEventListener('change', function () { calendar.refetchEvents(); });
    [costCenter, aircraft, operator].forEach(function (field) {
      field.addEventListener('change', function () { calendar.refetchEvents(); });
    });
  });
})();
