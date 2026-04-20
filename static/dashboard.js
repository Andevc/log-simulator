/**
 * dashboard.js
 * Consulta los endpoints REST de Flask cada 1 segundo
 * y actualiza graficas, KPIs, IPs bloqueadas e historial.
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
  endpoints: [
    '#00d4aa','#0099ff','#ff6b35','#9b59b6',
    '#f39c12','#1abc9c','#e74c3c','#3498db',
    '#ff3b5c','#2ecc71',
  ],
};

// ─── Config global de Chart.js ────────────────────────────────────────────────

Chart.defaults.color       = C.muted;
Chart.defaults.font.family = "'JetBrains Mono', monospace";
Chart.defaults.font.size   = 11;
Chart.defaults.borderColor = C.border;

// ─── Estado ───────────────────────────────────────────────────────────────────

var charts  = {};
var MOTIVOS = [];
var NIVELES = [];
var isRefreshing = false;
var refreshTick = 0;
var FAST_REFRESH_MS = 1000;
var CHARTS_EVERY_TICKS = 5;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmt(n) {
  if (n === null || n === undefined) return '—';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000)    return (n / 1000).toFixed(1) + 'K';
  return String(n);
}

function animateValue(el, newVal) {
  if (!el) return;
  el.textContent = newVal;
}

function codigoBadgeClass(codigo) {
  if (codigo >= 500) return 'code-5xx';
  if (codigo >= 400) return 'code-4xx';
  if (codigo >= 300) return 'code-3xx';
  return 'code-2xx';
}

function metodoBadgeClass(metodo) {
  var map = { GET: 'badge-get', POST: 'badge-post', PUT: 'badge-put', DELETE: 'badge-delete' };
  return map[metodo] || 'badge-get';
}

function shortEndpoint(ep) {
  return ep.replace('/api/', '/');
}

// ─── Inicializacion de graficas ───────────────────────────────────────────────

function initCharts() {
  var baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 400 },
    plugins: { legend: { display: false } },
  };

  // Linea: trafico por hora
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

  // Dona: top endpoints
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
                return chart.data.labels.map(function(label, i) {
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

  // Barras: errores 5xx por hora
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

  // Barras horizontales: latencia por endpoint
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
               ticks: { callback: function(val) {
                 return shortEndpoint(this.getLabelForValue(val));
               }}},
        },
      },
    }
  );
}

// ─── Fetch base ───────────────────────────────────────────────────────────────

async function fetchJSON(url) {
  var res = await fetch(url);
  if (!res.ok) throw new Error('HTTP ' + res.status + ' en ' + url);
  return res.json();
}

// ─── KPIs ─────────────────────────────────────────────────────────────────────

async function actualizarKPIs() {
  var data = await fetchJSON('/stats/kpis');
  animateValue(document.getElementById('kpi-total'),    fmt(data.total));
  animateValue(document.getElementById('kpi-errores'),  fmt(data.errores));
  animateValue(document.getElementById('kpi-tasa'),     data.tasa_error + '%');
  animateValue(document.getElementById('kpi-latencia'), data.latencia + 'ms');
  return data;
}

// ─── Graficas ─────────────────────────────────────────────────────────────────

async function actualizarTrafico() {
  var data = await fetchJSON('/stats/trafico');
  charts.trafico.data.labels = data.map(function(d) { return d.hora; });
  charts.trafico.data.datasets[0].data = data.map(function(d) { return d.requests; });
  charts.trafico.update();
}

async function actualizarEndpoints() {
  var data = await fetchJSON('/stats/top-endpoints');
  charts.endpoints.data.labels = data.map(function(d) { return d.endpoint; });
  charts.endpoints.data.datasets[0].data = data.map(function(d) { return d.total; });
  charts.endpoints.update();
}

async function actualizarErrores() {
  var data = await fetchJSON('/stats/errores');
  charts.errores.data.labels = data.map(function(d) { return d.hora; });
  charts.errores.data.datasets[0].data = data.map(function(d) { return d.errores; });
  charts.errores.update();
}

async function actualizarLatencia() {
  var data = await fetchJSON('/stats/latencia');
  charts.latencia.data.labels = data.map(function(d) { return d.endpoint; });
  charts.latencia.data.datasets[0].data = data.map(function(d) { return d.latencia_promedio; });
  charts.latencia.update();
}

// ─── Tabla de logs recientes ──────────────────────────────────────────────────

async function actualizarTabla() {
  var data  = await fetchJSON('/logs/recientes');
  var tbody = document.getElementById('tabla-logs');
  if (!tbody) return;

  if (!data || data.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:20px">Sin datos</td></tr>';
    return;
  }

  var html = '';
  data.forEach(function(log) {
    var codigoClass = codigoBadgeClass(log.codigo);
    var metodoClass = metodoBadgeClass(log.metodo);
    html +=
      '<tr>' +
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

// ─── Timestamp ────────────────────────────────────────────────────────────────

function actualizarTimestamp() {
  var ahora = new Date();
  var h = String(ahora.getHours()).padStart(2, '0');
  var m = String(ahora.getMinutes()).padStart(2, '0');
  var s = String(ahora.getSeconds()).padStart(2, '0');
  document.getElementById('last-update').textContent = 'actualizado ' + h + ':' + m + ':' + s;
}

// ─── Opciones del CRUD (se cargan una sola vez al inicio) ─────────────────────

async function cargarOpciones() {
  try {
    var data = await fetchJSON('/ips/motivos');
    MOTIVOS  = data.motivos;
    NIVELES  = data.niveles;
  } catch (e) {
    MOTIVOS = [
      'Actividad sospechosa', 'Demasiados errores 500', 'Fuerza bruta detectada',
      'IP desconocida', 'Acceso no autorizado', 'Mantenimiento',
    ];
    NIVELES = ['BAJO', 'MEDIO', 'ALTO'];
  }

  // Poblar el select de motivo del formulario de bloqueo
  var selMotivo = document.getElementById('select-motivo-nuevo');
  var selNivel  = document.getElementById('select-nivel-nuevo');

  if (selMotivo) {
    MOTIVOS.forEach(function(m) {
      var opt = document.createElement('option');
      opt.value = m;
      opt.textContent = m;
      selMotivo.appendChild(opt);
    });
  }
  if (selNivel) {
    NIVELES.forEach(function(n) {
      var opt = document.createElement('option');
      opt.value = n;
      opt.textContent = n;
      selNivel.appendChild(opt);
    });
  }
}

// ─── CRUD IPs bloqueadas ──────────────────────────────────────────────────────

async function actualizarIPsBloqueadas() {
  var data  = await fetchJSON('/ips/bloqueadas');
  var lista = document.getElementById('lista-ips');
  if (!lista) return;

  if (!data || data.length === 0) {
    lista.innerHTML = '<div class="ips-empty">Sin IPs bloqueadas</div>';
    return;
  }

  var motivosOpts = MOTIVOS.map(function(m) {
    return '<option value="' + m + '">' + m + '</option>';
  }).join('');

  var nivelesOpts = NIVELES.map(function(n) {
    return '<option value="' + n + '">' + n + '</option>';
  }).join('');

  var html = '';
  data.forEach(function(item) {
    var key        = item.ip.replace(/\./g, '-');
    var nivelClass = item.nivel === 'ALTO' ? 'nivel-alto'
                   : item.nivel === 'MEDIO' ? 'nivel-medio'
                   : 'nivel-bajo';

    var mOpts = motivosOpts.replace(
      'value="' + item.motivo + '"',
      'value="' + item.motivo + '" selected'
    );
    var nOpts = nivelesOpts.replace(
      'value="' + item.nivel + '"',
      'value="' + item.nivel + '" selected'
    );

    html +=
      '<div class="ip-row" id="row-' + key + '">' +
        '<div class="ip-info">' +
          '<div class="ip-addr">' +
            item.ip +
            ' <span class="nivel-badge ' + nivelClass + '">' + item.nivel + '</span>' +
            ' <span class="intentos-badge">' + item.intentos + ' intentos</span>' +
          '</div>' +
          '<div class="ip-meta">' + item.bloqueada_en + '</div>' +
        '</div>' +
        '<div class="ip-editar">' +
          '<select class="ip-select" id="motivo-' + key + '">' + mOpts + '</select>' +
          '<select class="ip-select" id="nivel-'  + key + '">' + nOpts + '</select>' +
          '<button class="btn-guardar"     onclick="editarIP(\''      + item.ip + '\')">Guardar</button>' +
          '<button class="btn-desbloquear" onclick="desbloquearIP(\'' + item.ip + '\')">Eliminar</button>' +
        '</div>' +
      '</div>';
  });
  lista.innerHTML = html;
}

function bloquearIPManual() {
  var inputIP  = document.getElementById('input-ip-bloquear');
  var selMot   = document.getElementById('select-motivo-nuevo');
  var selNiv   = document.getElementById('select-nivel-nuevo');
  var ip       = (inputIP ? inputIP.value : '').trim();
  var motivo   = selMot ? selMot.value : 'Actividad sospechosa';
  var nivel    = selNiv ? selNiv.value : 'BAJO';

  if (!ip) { alert('Ingresa una IP'); return; }

  fetch('/ips/bloquear', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ip: ip, motivo: motivo, nivel: nivel }),
  })
  .then(function() {
    if (inputIP) inputIP.value = '';
    actualizarIPsBloqueadas();
  })
  .catch(function(err) { console.error('Error al bloquear:', err); });
}

function editarIP(ip) {
  var key    = ip.replace(/\./g, '-');
  var motivo = document.getElementById('motivo-' + key);
  var nivel  = document.getElementById('nivel-'  + key);
  if (!motivo || !nivel) return;

  fetch('/ips/editar/' + encodeURIComponent(ip), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ motivo: motivo.value, nivel: nivel.value }),
  })
  .then(function() { actualizarIPsBloqueadas(); })
  .catch(function(err) { console.error('Error al editar:', err); });
}

function desbloquearIP(ip) {
  fetch('/ips/desbloquear/' + encodeURIComponent(ip), { method: 'DELETE' })
    .then(function() {
      actualizarIPsBloqueadas();
      actualizarHistorial();
    })
    .catch(function(err) { console.error('Error al desbloquear:', err); });
}

// ─── Historial de intentos bloqueados ────────────────────────────────────────

async function actualizarHistorial() {
  var data  = await fetchJSON('/ips/historial');
  var lista = document.getElementById('historial-lista');
  if (!lista) return;

  if (!data || data.length === 0) {
    lista.innerHTML = '<div class="ips-empty">Sin intentos registrados</div>';
    return;
  }

  var html = '';
  data.forEach(function(item) {
    var mClass = 'm-' + (item.metodo || 'get').toLowerCase();
    html +=
      '<div class="historial-item">' +
        '<span class="hist-ts">'       + item.ts       + '</span>' +
        '<span class="hist-ip">'       + item.ip       + '</span>' +
        '<span class="feed-metodo '    + mClass + '" style="font-size:10px">' + item.metodo + '</span>' +
        '<span class="hist-endpoint">' + item.endpoint + '</span>' +
      '</div>';
  });
  lista.innerHTML = html;
}

// ─── Alertas automaticas ──────────────────────────────────────────────────────

function verificarAlertas(kpis) {
  var bannerTasa = document.getElementById('alerta-tasa');
  var bannerLat  = document.getElementById('alerta-latencia');
  var valTasa    = document.getElementById('val-tasa');
  var valLat     = document.getElementById('val-lat');
  if (!bannerTasa || !bannerLat || !kpis) return;

  if (kpis.tasa_error > 10) {
    bannerTasa.style.display = 'flex';
    if (valTasa) valTasa.textContent = kpis.tasa_error + '%';
  } else {
    bannerTasa.style.display = 'none';
  }

  if (kpis.latencia > 800) {
    bannerLat.style.display = 'flex';
    if (valLat) valLat.textContent = kpis.latencia + 'ms';
  } else {
    bannerLat.style.display = 'none';
  }
}

async function actualizarKPIsYAlertas() {
  var kpis = await actualizarKPIs();
  verificarAlertas(kpis);
}

// ─── Ciclo de refresco ────────────────────────────────────────────────────────

async function refreshAll() {
  if (isRefreshing) return;
  isRefreshing = true;
  refreshTick += 1;

  var tareas = [
    actualizarKPIsYAlertas,
    actualizarTabla,
    actualizarIPsBloqueadas,
    actualizarHistorial,
  ];

  if (refreshTick % CHARTS_EVERY_TICKS === 0) {
    tareas.push(
      actualizarTrafico,
      actualizarEndpoints,
      actualizarErrores,
      actualizarLatencia
    );
  }

  try {
    var resultados = await Promise.allSettled(
      tareas.map(function(tarea) { return tarea(); })
    );

    var huboError = resultados.some(function(r) { return r.status === 'rejected'; });
    actualizarTimestamp();
    if (huboError) {
      document.getElementById('last-update').textContent += ' · parcial';
    }
  } catch (err) {
    console.error('Error al obtener datos:', err);
    document.getElementById('last-update').textContent = 'error de conexion';
  } finally {
    isRefreshing = false;
  }
}

// ─── Arranque ─────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
  initCharts();
  cargarOpciones().then(function() {
    // Primera carga con graficas para evitar esperar 5 ciclos.
    refreshTick = CHARTS_EVERY_TICKS - 1;
    refreshAll();
    setInterval(refreshAll, FAST_REFRESH_MS);
  });
});