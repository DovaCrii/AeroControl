// Dashboard charts. Extracted from inline <script> blocks in dashboard/index.html
// so the page carries no inline JavaScript (MASTER_PLAN V.10). Reads the figures
// from the #chart-data json_script and each chart's translated series label from
// the canvas element's data-label attribute. Loads after the deferred Chart.js
// vendor bundle.
(function () {
  var dataNode = document.getElementById('chart-data');
  if (!dataNode || typeof Chart === 'undefined') return;
  var chartData = JSON.parse(dataNode.textContent);

  function labelFor(id) {
    var el = document.getElementById(id);
    return el ? el.dataset.label || '' : '';
  }

  // The navy first slot was invisible in dark mode (1.16:1 against the card),
  // so the palette is picked per theme and re-applied on theme change.
  var palettes = {
    light: ['#1B2A4A', '#2EC4B6', '#E76F51', '#F4A261', '#2A9D8F', '#6B4CE6', '#E63946', '#457B9D'],
    dark: ['#5B8FD9', '#42D4C6', '#F08A6B', '#F4B266', '#4FBFAE', '#A184F0', '#F2606D', '#6FA8CF'],
  };
  var isDark = function () { return document.documentElement.dataset.theme === 'dark'; };
  var palette = isDark() ? palettes.dark : palettes.light;
  var textColor = getComputedStyle(document.body).color;
  var charts = [];
  // LV-109: a chart is built only when **both** halves are there -- its data and
  // its canvas. The panel kept building two charts LV-89 had already removed
  // from the template, and Chart.js throwing on the missing canvas took down
  // every chart declared after it: the two that *were* on the page never
  // appeared, so the panel showed two empty boxes and two console errors on
  // every load. The comment below already described this exact failure for
  // missing **data**; this is its other half, and the half that actually bit.
  function build(id, data, config) {
    var canvas = document.getElementById(id);
    if (!canvas || !data || !data.length) return;
    charts.push(new Chart(canvas, config));
  }

  // LV-89 replaced "Aircraft by status" and "Permissions by status" with the
  // three-indicator strip; their canvases are gone from the template, so no
  // chart is declared for them here either. The view still computes the two
  // series (a test reads `permissions_by_status` as evidence of the cost-centre
  // filter), which is why `chart-data` still carries them.

  // ── Maintenance by Type (doughnut) ──
  var maintData = chartData.maintenance_by_type;
  build('chart-maint-type', maintData, {
    type: 'doughnut',
    data: {
      labels: maintData.map(function (d) { return d.maintenance_type; }),
      datasets: [{
        data: maintData.map(function (d) { return d.count; }),
        backgroundColor: palette.slice(0, maintData.length),
      }]
    },
    options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { color: textColor } } } }
  });

  // LV-78/LV-89: "Tasks per Stage" removed with the Kanban board's retirement.
  // The view no longer sends `tasks_by_stage`, so reading it here would throw on
  // `.length` and take every chart below it down with the same script.

  // ── Monthly Flights (line) ──
  var flightData = chartData.monthly_flights;
  build('chart-monthly-flights', flightData, {
      type: 'line',
      data: {
        labels: flightData.map(function (d) { return d.month ? new Date(d.month).toLocaleString('default', { month: 'short', year: '2-digit' }) : ''; }),
        datasets: [{
          label: labelFor('chart-monthly-flights'),
          data: flightData.map(function (d) { return d.count; }),
          borderColor: '#2EC4B6',
          backgroundColor: 'rgba(46,196,182,0.15)',
          fill: true,
          tension: 0.3,
          pointBackgroundColor: '#2EC4B6',
        }]
      },
      options: {
        responsive: true,
        plugins: { legend: { labels: { color: textColor } } },
        scales: { y: { beginAtZero: true, ticks: { color: textColor } }, x: { ticks: { color: textColor } } }
      }
  });

  // Recolour on theme change: base.html already emits aero:themechange, but
  // nothing listened, so axes/legends kept the previous theme's colours until
  // a reload.
  document.addEventListener('aero:themechange', function () {
    palette = isDark() ? palettes.dark : palettes.light;
    var color = getComputedStyle(document.body).color;
    charts.forEach(function (chart) {
      chart.data.datasets.forEach(function (dataset) {
        if (Array.isArray(dataset.backgroundColor)) {
          dataset.backgroundColor = palette.slice(0, dataset.backgroundColor.length);
        }
      });
      var legend = chart.options.plugins && chart.options.plugins.legend;
      if (legend && legend.labels) legend.labels.color = color;
      Object.values(chart.options.scales || {}).forEach(function (scale) {
        if (scale && scale.ticks) scale.ticks.color = color;
      });
      chart.update();
    });
  });
})();
