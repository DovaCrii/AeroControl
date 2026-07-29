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
  var track = function (chart) { if (chart) charts.push(chart); return chart; };

  // ── Aircraft by Status (doughnut) ──
  var acData = chartData.aircraft_by_status;
  if (acData.length) {
    track(new Chart(document.getElementById('chart-aircraft-status'), {
      type: 'doughnut',
      data: {
        labels: acData.map(function (d) { return d.status; }),
        datasets: [{
          data: acData.map(function (d) { return d.count; }),
          backgroundColor: palette.slice(0, acData.length),
        }]
      },
      options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { color: textColor } } } }
    }));
  }

  // ── Permissions by Status (bar) ──
  var permData = chartData.permissions_by_status;
  if (permData.length) {
    track(new Chart(document.getElementById('statusChart'), {
      type: 'bar',
      data: {
        labels: permData.map(function (d) { return d.status; }),
        datasets: [{
          label: labelFor('statusChart'),
          data: permData.map(function (d) { return d.count; }),
          backgroundColor: palette.slice(0, permData.length),
        }]
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { color: textColor } }, x: { ticks: { color: textColor } } }
      }
    }));
  }

  // ── Maintenance by Type (doughnut) ──
  var maintData = chartData.maintenance_by_type;
  if (maintData.length) {
    track(new Chart(document.getElementById('chart-maint-type'), {
      type: 'doughnut',
      data: {
        labels: maintData.map(function (d) { return d.maintenance_type; }),
        datasets: [{
          data: maintData.map(function (d) { return d.count; }),
          backgroundColor: palette.slice(0, maintData.length),
        }]
      },
      options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { color: textColor } } } }
    }));
  }

  // ── Tasks per Stage (bar) ──
  var stageData = chartData.tasks_by_stage;
  if (stageData.length) {
    track(new Chart(document.getElementById('stagesChart'), {
      type: 'bar',
      data: {
        labels: stageData.map(function (d) { return d.name; }),
        datasets: [{
          label: labelFor('stagesChart'),
          data: stageData.map(function (d) { return d.count; }),
          backgroundColor: '#2EC4B6',
        }]
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { color: textColor, stepSize: 1 } }, x: { ticks: { color: textColor } } }
      }
    }));
  }

  // ── Monthly Flights (line) ──
  var flightData = chartData.monthly_flights;
  if (flightData.length) {
    track(new Chart(document.getElementById('chart-monthly-flights'), {
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
    }));
  }

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
