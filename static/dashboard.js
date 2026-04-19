/**
 * dashboard.js
 * Consulta los endpoints REST de Flask cada 3 segundos
 * y actualiza las graficas y KPIs del dashboard.
 */

'use strict';

// ─── Paleta de colores ────────────────────────────────────────────────────────

const C = {
  accent:  '#00d4aa',
  accent2: '#0099ff',
  warn:    '#ff6b35',
  danger:  '#ff3b5c',
  muted:   '#6b7a99',
  border:  '#1e2430',
  surface: '#161a22',
  text:    '#e2e8f0',
  // Colores para dona/barras de endpoints
  endpoints: [
    '#00d4aa','#0099ff','#ff6b35','#9b59b6',
    '#f39c12','#1abc9c','#e74c3c','#3498db',
    '#ff3b5c','#2ecc71',
  ],
};

// ─── Config global de Chart.js ────────────────────────────────────────────────

Chart.defaults.color          = C.muted;
Chart.defaults.font.family    = "'JetBrains Mono', monospace";
Chart.defaults.font.size      = 11;
Chart.defaults.borderColor    = C.border;

// ─── Estado de las graficas ───────────────────────────────────────────────────

let charts = {};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmt(n) {
  if (n === null || n === undefined) return '—';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

function animateValue(el, newVal, formatter) {
  if (!el) return;
  el.textContent = formatter ? formatter(newVal) : newVal;
}

function codigoBadgeClass(codigo) {
  if (codigo >= 500) return 'code-5xx';
  if (codigo >= 400) return 'code-4xx';
  if (codigo >= 300) return 'code-3xx';
  return 'code-2xx';
}

function metodoBadgeClass(metodo) {
  const map = { GET: 'badge-get', POST: 'badge-post', PUT: 'badge-put', DELETE: 'badge-delete' };
  return map[metodo] || 'badge-get';
}

function shortEndpoint(ep) {
  return ep.replace('/api/', '/');
}

// ─── Inicializacion de graficas ───────────────────────────────────────────────

function initCharts() {
  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 400 },
    plugins: { legend: { display: false } },
  };

  // Grafica de linea: trafico por hora
  charts.trafico = new Chart(
    document.getElementById('chart-trafico').getContext('2d'),
    {
      type: 'line',
      data: { labels: [], datasets: [{
        label: 'Requests',
        data: [],
        borderColor: C.accent,
        backgroundColor: 'rgba(0,212,170,0.08)',
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: C.accent,
        tension: 0.4,
        fill: true,
      }]},
      options: {
        ...baseOptions,
        scales: {
          x: { grid: { color: C.border }, ticks: { maxTicksLimit: 12 } },
          y: { grid: { color: C.border }, beginAtZero: true },
        },
        plugins: {
          ...baseOptions.plugins,
          tooltip: { mode: 'index', intersect: false },
        },
      },
    }
  );

  // Grafica de dona: top endpoints
  charts.endpoints = new Chart(
    document.getElementById('chart-endpoints').getContext('2d'),
    {
      type: 'doughnut',
      data: { labels: [], datasets: [{
        data: [],
        backgroundColor: C.endpoints,
        borderColor: C.surface,
        borderWidth: 3,
        hoverOffset: 8,
      }]},
      options: {
        ...baseOptions,
        cutout: '62%',
        plugins: {
          legend: {
            display: true,
            position: 'right',
            labels: {
              color: C.muted,
              font: { size: 10 },
              boxWidth: 10,
              padding: 8,
              generateLabels: function(chart) {
                const data = chart.data;
                return data.labels.map(function(label, i) {
                  return {
                    text: shortEndpoint(label),
                    fillStyle: C.endpoints[i % C.endpoints.length],
                    strokeStyle: C.surface,
                    lineWidth: 2,
                    index: i,
                  };
                });
              },
            },
          },
        },
      },
    }
  );

  // Grafica de barras: errores 5xx por hora
  charts.errores = new Chart(
    document.getElementById('chart-errores').getContext('2d'),
    {
      type: 'bar',
      data: { labels: [], datasets: [{
        label: 'Errores 5xx',
        data: [],
        backgroundColor: 'rgba(255,59,92,0.7)',
        borderColor: C.danger,
        borderWidth: 1,
        borderRadius: 4,
      }]},
      options: {
        ...baseOptions,
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
          y: { grid: { color: C.border }, beginAtZero: true },
        },
      },
    }
  );

  // Grafica de barras horizontales: latencia por endpoint
  charts.latencia = new Chart(
    document.getElementById('chart-latencia').getContext('2d'),
    {
      type: 'bar',
      data: { labels: [], datasets: [{
        label: 'Latencia (ms)',
        data: [],
        backgroundColor: 'rgba(0,153,255,0.7)',
        borderColor: C.accent2,
        borderWidth: 1,
        borderRadius: 4,
      }]},
      options: {
        ...baseOptions,
        indexAxis: 'y',
        scales: {
          x: { grid: { color: C.border }, beginAtZero: true,
               title: { display: true, text: 'ms', color: C.muted } },
          y: { grid: { display: false },
               ticks: { callback: function(val, idx) {
                 return shortEndpoint(this.getLabelForValue(val));
               }}},
        },
      },
    }
  );
}

// ─── Actualizacion de datos ───────────────────────────────────────────────────

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error('HTTP ' + res.status + ' en ' + url);
  return res.json();
}

async function actualizarKPIs() {
  const data = await fetchJSON('/stats/kpis');
  animateValue(document.getElementById('kpi-total'),   fmt(data.total));
  animateValue(document.getElementById('kpi-errores'), fmt(data.errores));
  animateValue(document.getElementById('kpi-tasa'),    data.tasa_error + '%');
  animateValue(document.getElementById('kpi-latencia'), data.latencia + 'ms');
}

async function actualizarTrafico() {
  const data = await fetchJSON('/stats/trafico');
  charts.trafico.data.labels   = data.map(function(d) { return d.hora; });
  charts.trafico.data.datasets[0].data = data.map(function(d) { return d.requests; });
  charts.trafico.update();
}

async function actualizarEndpoints() {
  const data = await fetchJSON('/stats/top-endpoints');
  charts.endpoints.data.labels = data.map(function(d) { return d.endpoint; });
  charts.endpoints.data.datasets[0].data = data.map(function(d) { return d.total; });
  charts.endpoints.update();
}

async function actualizarErrores() {
  const data = await fetchJSON('/stats/errores');
  charts.errores.data.labels   = data.map(function(d) { return d.hora; });
  charts.errores.data.datasets[0].data = data.map(function(d) { return d.errores; });
  charts.errores.update();
}

async function actualizarLatencia() {
  const data = await fetchJSON('/stats/latencia');
  charts.latencia.data.labels  = data.map(function(d) { return d.endpoint; });
  charts.latencia.data.datasets[0].data = data.map(function(d) { return d.latencia_promedio; });
  charts.latencia.update();
}

async function actualizarTabla() {
  const data = await fetchJSON('/logs/recientes');
  const tbody = document.getElementById('tabla-logs');

  if (!data || data.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:20px">Sin datos</td></tr>';
    return;
  }

  var html = '';
  data.forEach(function(log) {
    var codigoClass = codigoBadgeClass(log.codigo);
    var metodoClass = metodoBadgeClass(log.metodo);
    html += '<tr>' +
      '<td>' + log.timestamp + '</td>' +
      '<td style="color:var(--muted)">' + log.ip + '</td>' +
      '<td><span class="badge ' + metodoClass + '">' + log.metodo + '</span></td>' +
      '<td style="color:var(--text)">' + log.endpoint + '</td>' +
      '<td><span class="' + codigoClass + '">' + log.codigo + '</span></td>' +
      '<td style="color:var(--muted)">' + log.latencia_ms + ' ms</td>' +
      '</tr>';
  });
  tbody.innerHTML = html;
}

function actualizarTimestamp() {
  var ahora = new Date();
  var h = String(ahora.getHours()).padStart(2, '0');
  var m = String(ahora.getMinutes()).padStart(2, '0');
  var s = String(ahora.getSeconds()).padStart(2, '0');
  document.getElementById('last-update').textContent = 'actualizado ' + h + ':' + m + ':' + s;
}

// ─── Ciclo de refresco ────────────────────────────────────────────────────────

async function refreshAll() {
  try {
    await Promise.all([
      actualizarKPIs(),
      actualizarTrafico(),
      actualizarEndpoints(),
      actualizarErrores(),
      actualizarLatencia(),
      actualizarTabla(),
    ]);
    actualizarTimestamp();
  } catch (err) {
    console.error('Error al obtener datos:', err);
    document.getElementById('last-update').textContent = 'error de conexion';
  }
}

// ─── Arranque ─────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
  initCharts();
  refreshAll();
  setInterval(refreshAll, 3000);
});
