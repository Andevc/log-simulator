/**
 * dashboard.js — Log Simulator
 * 14 análisis en tiempo real, refresco cada 3 segundos.
 */

'use strict';

// ─── Paleta ───────────────────────────────────────────────────────────────────

var C = {
  accent:  '#00a884',
  accent2: '#0077cc',
  warn:    '#d95f1a',
  danger:  '#cc1f3c',
  muted:   '#5a6480',
  border:  '#dde1e9',
  surface: '#f0f2f5',
  text:    '#1a1f2e',
  endpoints: [
    '#00a884','#0077cc','#d95f1a','#7c3aed',
    '#b45309','#0891b2','#be123c','#1d4ed8',
    '#cc1f3c','#16a34a',
  ],
  metodos: { GET: '#0077cc', POST: '#00a884', PUT: '#d95f1a', DELETE: '#cc1f3c' },
};

Chart.defaults.color            = C.text;
Chart.defaults.font.family      = "'JetBrains Mono', monospace";
Chart.defaults.font.size        = 11;
Chart.defaults.borderColor      = C.border;

var charts  = {};
var MOTIVOS = [];
var NIVELES = [];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(n) {
  if (n === null || n === undefined) return '—';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000)    return (n / 1000).toFixed(1) + 'K';
  return String(n);
}
function animateValue(el, v) { if (el) el.textContent = v; }
function codigoBadgeClass(c) {
  if (c >= 500) return 'code-5xx';
  if (c >= 400) return 'code-4xx';
  if (c >= 300) return 'code-3xx';
  return 'code-2xx';
}
function metodoBadgeClass(m) {
  return { GET:'badge-get', POST:'badge-post', PUT:'badge-put', DELETE:'badge-delete' }[m] || 'badge-get';
}
function shortEp(ep) { return ep.replace('/api/', '/'); }
function colorCodigo(c) {
  if (c >= 500) return C.danger;
  if (c >= 400) return C.warn;
  if (c >= 300) return C.accent2;
  return C.accent;
}

async function fetchJSON(url) {
  var res = await fetch(url);
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

// ─── Init gráficas ────────────────────────────────────────────────────────────

function initCharts() {
  var base = {
    responsive: true, maintainAspectRatio: false,
    animation: { duration: 400 },
    plugins: { legend: { display: false } },
  };

  // 1. Tráfico por hora
  charts.trafico = new Chart(document.getElementById('chart-trafico').getContext('2d'), {
    type: 'line',
    data: { labels: [], datasets: [{ label:'Requests', data:[], borderColor:C.accent,
      backgroundColor:'rgba(0,168,132,0.1)', borderWidth:2, pointRadius:3,
      pointBackgroundColor:C.accent, tension:0.4, fill:true }]},
    options: { ...base, scales: {
      x: { grid:{color:C.border}, ticks:{color:C.muted, maxTicksLimit:12} },
      y: { grid:{color:C.border}, ticks:{color:C.muted}, beginAtZero:true },
    }, plugins: { ...base.plugins, tooltip:{
      mode:'index', intersect:false,
      backgroundColor:'#ffffff', titleColor:C.text, bodyColor:C.muted,
      borderColor:C.border, borderWidth:1,
    }}},
  });

  // 2. Dona endpoints
  charts.endpoints = new Chart(document.getElementById('chart-endpoints').getContext('2d'), {
    type: 'doughnut',
    data: { labels:[], datasets:[{ data:[], backgroundColor:C.endpoints,
      borderColor:'#ffffff', borderWidth:3, hoverOffset:8 }]},
    options: { ...base, cutout:'62%', plugins: { legend: { display:true, position:'right',
      labels:{ color:C.muted, font:{size:10}, boxWidth:10, padding:8,
        generateLabels: function(chart) {
          return chart.data.labels.map(function(l,i) {
            return { text:shortEp(l), fillStyle:C.endpoints[i%C.endpoints.length],
              strokeStyle:'#ffffff', lineWidth:2, index:i };
          });
        }
      }
    }}},
  });

  // 3. Barras errores/hora
  charts.errores = new Chart(document.getElementById('chart-errores').getContext('2d'), {
    type: 'bar',
    data: { labels:[], datasets:[{ label:'Errores 5xx', data:[],
      backgroundColor:'rgba(204,31,60,0.65)', borderColor:C.danger, borderWidth:1, borderRadius:4 }]},
    options: { ...base, scales: {
      x:{ grid:{display:false}, ticks:{color:C.muted, maxTicksLimit:8} },
      y:{ grid:{color:C.border}, ticks:{color:C.muted}, beginAtZero:true },
    }, plugins: { ...base.plugins, tooltip:{
      backgroundColor:'#ffffff', titleColor:C.text, bodyColor:C.muted,
      borderColor:C.border, borderWidth:1,
    }}},
  });

  // 4. Barras horiz latencia/endpoint
  charts.latencia = new Chart(document.getElementById('chart-latencia').getContext('2d'), {
    type: 'bar',
    data: { labels:[], datasets:[{ label:'Latencia (ms)', data:[],
      backgroundColor:'rgba(0,119,204,0.65)', borderColor:C.accent2, borderWidth:1, borderRadius:4 }]},
    options: { ...base, indexAxis:'y', scales: {
      x:{ grid:{color:C.border}, ticks:{color:C.muted}, beginAtZero:true, title:{display:true,text:'ms',color:C.muted} },
      y:{ grid:{display:false}, ticks:{ color:C.muted, callback: function(v) { return shortEp(this.getLabelForValue(v)); }}},
    }, plugins: { ...base.plugins, tooltip:{
      backgroundColor:'#ffffff', titleColor:C.text, bodyColor:C.muted,
      borderColor:C.border, borderWidth:1,
    }}},
  });

  // 5. Dona codigos HTTP
  charts.codigos = new Chart(document.getElementById('chart-codigos').getContext('2d'), {
    type: 'doughnut',
    data: { labels:[], datasets:[{ data:[], backgroundColor:[], borderColor:'#ffffff', borderWidth:3, hoverOffset:8 }]},
    options: { ...base, cutout:'60%', plugins:{ legend:{ display:true, position:'right',
      labels:{ color:C.muted, font:{size:10}, boxWidth:10, padding:10 } }}},
  });

  // 6. Dona metodos HTTP
  charts.metodos = new Chart(document.getElementById('chart-metodos').getContext('2d'), {
    type: 'doughnut',
    data: { labels:[], datasets:[{ data:[], backgroundColor:[C.accent2,C.accent,C.warn,C.danger],
      borderColor:'#ffffff', borderWidth:3, hoverOffset:8 }]},
    options: { ...base, cutout:'60%', plugins:{ legend:{ display:true, position:'right',
      labels:{ color:C.muted, font:{size:11}, boxWidth:12, padding:12 } }}},
  });

  // 7. Barras horiz tasa error/endpoint
  charts.tasaEndpoint = new Chart(document.getElementById('chart-tasa-endpoint').getContext('2d'), {
    type: 'bar',
    data: { labels:[], datasets:[{ label:'Tasa de error (%)', data:[],
      backgroundColor:'rgba(217,95,26,0.65)', borderColor:C.warn, borderWidth:1, borderRadius:4 }]},
    options: { ...base, indexAxis:'y', scales: {
      x:{ grid:{color:C.border}, ticks:{color:C.muted}, beginAtZero:true, max:100, title:{display:true,text:'%',color:C.muted} },
      y:{ grid:{display:false}, ticks:{ color:C.muted, callback: function(v) { return shortEp(this.getLabelForValue(v)); }}},
    }, plugins: { ...base.plugins, tooltip:{
      backgroundColor:'#ffffff', titleColor:C.text, bodyColor:C.muted,
      borderColor:C.border, borderWidth:1,
    }}},
  });

  // 8. Línea latencia/hora
  charts.latenciaHora = new Chart(document.getElementById('chart-latencia-hora').getContext('2d'), {
    type: 'line',
    data: { labels:[], datasets:[{ label:'Latencia (ms)', data:[], borderColor:C.accent2,
      backgroundColor:'rgba(0,119,204,0.1)', borderWidth:2, pointRadius:3,
      pointBackgroundColor:C.accent2, tension:0.4, fill:true }]},
    options: { ...base, scales: {
      x:{ grid:{color:C.border}, ticks:{color:C.muted, maxTicksLimit:12} },
      y:{ grid:{color:C.border}, ticks:{color:C.muted}, beginAtZero:true, title:{display:true,text:'ms',color:C.muted} },
    }, plugins:{ ...base.plugins, tooltip:{
      mode:'index', intersect:false,
      backgroundColor:'#ffffff', titleColor:C.text, bodyColor:C.muted,
      borderColor:C.border, borderWidth:1,
    }}},
  });

  // 9. (scatter y percentiles eliminados)

  // 10. Barras agrupadas: cruce de tablas (volumen vs errores por endpoint)
  charts.cruce = new Chart(document.getElementById('chart-cruce').getContext('2d'), {
    type: 'bar',
    data: { labels:[], datasets:[
      {
        label: 'Total Requests (logs_por_endpoint)',
        data: [],
        backgroundColor: 'rgba(0,119,204,0.65)',
        borderColor: C.accent2,
        borderWidth: 1,
        borderRadius: 4,
      },
      {
        label: 'Errores 5xx (logs_por_hora)',
        data: [],
        backgroundColor: 'rgba(204,31,60,0.65)',
        borderColor: C.danger,
        borderWidth: 1,
        borderRadius: 4,
      },
    ]},
    options: {
      ...base,
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: { color: C.muted, font:{ size:10 }, boxWidth:12, padding:14 },
        },
        tooltip: {
          backgroundColor:'#ffffff', titleColor:C.text, bodyColor:C.muted,
          borderColor:C.border, borderWidth:1,
        },
      },
      scales: {
        x: { grid:{ display:false }, ticks:{ color:C.muted,
             callback: function(v) { return shortEp(this.getLabelForValue(v)); }}},
        y: { grid:{ color:C.border }, ticks:{ color:C.muted }, beginAtZero:true },
      },
    },
  });
}

// ─── KPIs ─────────────────────────────────────────────────────────────────────

async function actualizarKPIs() {
  var data = await fetchJSON('/stats/kpis');
  animateValue(document.getElementById('kpi-total'),    fmt(data.total));
  animateValue(document.getElementById('kpi-errores'),  fmt(data.errores));
  animateValue(document.getElementById('kpi-tasa'),     data.tasa_error + '%');
  animateValue(document.getElementById('kpi-latencia'), data.latencia + 'ms');
}

// ─── Gráficas originales ──────────────────────────────────────────────────────

async function actualizarTrafico() {
  var data = await fetchJSON('/stats/trafico');
  charts.trafico.data.labels = data.map(function(d){return d.hora;});
  charts.trafico.data.datasets[0].data = data.map(function(d){return d.requests;});
  charts.trafico.update();
}
async function actualizarEndpoints() {
  var data = await fetchJSON('/stats/top-endpoints');
  charts.endpoints.data.labels = data.map(function(d){return d.endpoint;});
  charts.endpoints.data.datasets[0].data = data.map(function(d){return d.total;});
  charts.endpoints.update();
}
async function actualizarErrores() {
  var data = await fetchJSON('/stats/errores');
  charts.errores.data.labels = data.map(function(d){return d.hora;});
  charts.errores.data.datasets[0].data = data.map(function(d){return d.errores;});
  charts.errores.update();
}
async function actualizarLatencia() {
  var data = await fetchJSON('/stats/latencia');
  charts.latencia.data.labels = data.map(function(d){return d.endpoint;});
  charts.latencia.data.datasets[0].data = data.map(function(d){return d.latencia_promedio;});
  charts.latencia.update();
}
async function actualizarCodigos() {
  var data = await fetchJSON('/stats/codigos');
  var grupos = {'2xx':0,'3xx':0,'4xx':0,'5xx':0};
  data.forEach(function(d) {
    if      (d.codigo>=500) grupos['5xx']+=d.total;
    else if (d.codigo>=400) grupos['4xx']+=d.total;
    else if (d.codigo>=300) grupos['3xx']+=d.total;
    else                    grupos['2xx']+=d.total;
  });
  var labels  = Object.keys(grupos).filter(function(k){return grupos[k]>0;});
  var valores = labels.map(function(k){return grupos[k];});
  var colores = labels.map(function(k){return colorCodigo(parseInt(k));});
  charts.codigos.data.labels = labels;
  charts.codigos.data.datasets[0].data = valores;
  charts.codigos.data.datasets[0].backgroundColor = colores;
  charts.codigos.update();
}
async function actualizarMetodos() {
  var data = await fetchJSON('/stats/metodos');
  charts.metodos.data.labels = data.map(function(d){return d.metodo;});
  charts.metodos.data.datasets[0].data = data.map(function(d){return d.total;});
  charts.metodos.data.datasets[0].backgroundColor = data.map(function(d){return C.metodos[d.metodo]||C.muted;});
  charts.metodos.update();
}
async function actualizarTasaEndpoint() {
  var data = await fetchJSON('/stats/tasa-error-endpoint');
  charts.tasaEndpoint.data.labels = data.map(function(d){return d.endpoint;});
  charts.tasaEndpoint.data.datasets[0].data = data.map(function(d){return d.tasa_error;});
  charts.tasaEndpoint.data.datasets[0].backgroundColor = data.map(function(d){
    if (d.tasa_error>20) return 'rgba(204,31,60,0.65)';
    if (d.tasa_error>10) return 'rgba(217,95,26,0.65)';
    return 'rgba(0,168,132,0.65)';
  });
  charts.tasaEndpoint.update();
}
async function actualizarLatenciaHora() {
  var data = await fetchJSON('/stats/latencia-hora');
  charts.latenciaHora.data.labels = data.map(function(d){return d.hora;});
  charts.latenciaHora.data.datasets[0].data = data.map(function(d){return d.latencia;});
  charts.latenciaHora.update();
}

// ─── Análisis nuevos ──────────────────────────────────────────────────────────

async function actualizarCruce() {
  var data = await fetchJSON('/stats/cruce');
  charts.cruce.data.labels = data.map(function(d){ return d.endpoint; });
  charts.cruce.data.datasets[0].data = data.map(function(d){ return d.volumen; });
  charts.cruce.data.datasets[1].data = data.map(function(d){ return d.errores; });
  charts.cruce.update();
}

async function actualizarRPM() {
  var data = await fetchJSON('/stats/rpm');
  animateValue(document.getElementById('kpi-rpm'), data.rpm.toFixed(1));
}

async function actualizarDisponibilidad() {
  var data = await fetchJSON('/stats/disponibilidad');
  animateValue(document.getElementById('kpi-uptime'),   data.ratio + '%');
  animateValue(document.getElementById('kpi-fallidos'), fmt(data.fallidos));

  var bar   = document.getElementById('uptime-bar');
  var pct   = document.getElementById('uptime-pct');
  var ok    = document.getElementById('uptime-label-ok');
  var fail  = document.getElementById('uptime-label-fail');
  if (bar)  bar.style.width = data.ratio + '%';
  if (pct)  pct.textContent = data.ratio + '%';
  if (ok)   ok.textContent  = 'Exitosos: ' + fmt(data.exitosos);
  if (fail) fail.textContent = 'Fallidos: ' + fmt(data.fallidos);

  // Color de la barra según disponibilidad
  if (bar) {
    if (data.ratio >= 95)      bar.style.background = C.accent;
    else if (data.ratio >= 80) bar.style.background = C.warn;
    else                       bar.style.background = C.danger;
  }
}

async function actualizarHeatmap() {
  var data = await fetchJSON('/stats/heatmap');
  var cont = document.getElementById('heatmap-container');
  if (!cont) return;

  var max = Math.max.apply(null, data.map(function(d){return d.total;})) || 1;

  var html = '';
  data.forEach(function(d) {
    var ratio   = d.total / max;
    var opacity = Math.max(0.12, ratio);
    var r = 0, g = 168, b = 132;
    if (ratio > 0.7)      { r=204; g=31;  b=60;  }
    else if (ratio > 0.4) { r=0;   g=119; b=204; }

    var bg   = 'rgba(' + r + ',' + g + ',' + b + ',' + opacity.toFixed(2) + ')';
    var text = d.total > 0 ? fmt(d.total) : '';
    var hora = String(d.hora).padStart(2,'0') + 'h';

    html +=
      '<div class="heatmap-cell" style="background:' + bg + '" title="' + hora + ': ' + d.total + ' requests">' +
        '<span style="font-size:8px;color:var(--muted)">' + hora + '</span>' +
        '<span style="font-size:9px;color:var(--text)">'  + text + '</span>' +
      '</div>';
  });
  cont.innerHTML = html;
}

async function actualizarTopIPs() {
  var data = await fetchJSON('/stats/top-ips');
  var cont = document.getElementById('top-ips-container');
  if (!cont || !data || data.length === 0) return;

  var max = data[0].total || 1;
  var html = '';
  data.forEach(function(item, i) {
    var pct    = Math.round((item.total / max) * 100);
    var color  = item.bloqueada ? C.danger : C.accent2;
    var badge  = item.bloqueada
      ? '<span class="top-ip-badge-bloq">BLOQUEADA</span>'
      : '<button class="btn-bloquear-ip" onclick="bloquearDesdeTopIPs(\'' + item.ip + '\')">Bloquear</button>';

    html +=
      '<div class="top-ip-row">' +
        '<span class="top-ip-rank">#' + (i+1) + '</span>' +
        '<span class="top-ip-addr">' + item.ip + '</span>' +
        '<div class="top-ip-bar-wrap">' +
          '<div class="top-ip-bar" style="width:' + pct + '%;background:' + color + '"></div>' +
        '</div>' +
        '<span class="top-ip-count">' + fmt(item.total) + '</span>' +
        badge +
      '</div>';
  });
  cont.innerHTML = html;
}

function bloquearDesdeTopIPs(ip) {
  fetch('/ips/bloquear', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ip: ip, motivo: 'Actividad sospechosa', nivel: 'MEDIO' }),
  })
  .then(function() {
    actualizarTopIPs();
    actualizarIPsBloqueadas();
  })
  .catch(function(err) { console.error(err); });
}

// ─── Tabla logs recientes ─────────────────────────────────────────────────────

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
    html += '<tr>' +
      '<td>' + log.timestamp + '</td>' +
      '<td style="color:var(--muted)">' + log.ip + '</td>' +
      '<td><span class="badge ' + metodoBadgeClass(log.metodo) + '">' + log.metodo + '</span></td>' +
      '<td>' + log.endpoint + '</td>' +
      '<td><span class="' + codigoBadgeClass(log.codigo) + '">' + log.codigo + '</span></td>' +
      '<td style="color:var(--muted)">' + log.latencia_ms + ' ms</td>' +
      '</tr>';
  });
  tbody.innerHTML = html;
}

// ─── Timestamp ────────────────────────────────────────────────────────────────

function actualizarTimestamp() {
  var a = new Date();
  var h = String(a.getHours()).padStart(2,'0');
  var m = String(a.getMinutes()).padStart(2,'0');
  var s = String(a.getSeconds()).padStart(2,'0');
  document.getElementById('last-update').textContent = 'actualizado ' + h + ':' + m + ':' + s;
}

// ─── CRUD IPs ─────────────────────────────────────────────────────────────────

async function cargarOpciones() {
  try {
    var data = await fetchJSON('/ips/motivos');
    MOTIVOS = data.motivos; NIVELES = data.niveles;
  } catch(e) {
    MOTIVOS = ['Actividad sospechosa','Demasiados errores 500','Fuerza bruta detectada',
               'IP desconocida','Acceso no autorizado','Mantenimiento'];
    NIVELES = ['BAJO','MEDIO','ALTO'];
  }
  var sm = document.getElementById('select-motivo-nuevo');
  var sn = document.getElementById('select-nivel-nuevo');
  if (sm) MOTIVOS.forEach(function(m){ var o=document.createElement('option'); o.value=m; o.textContent=m; sm.appendChild(o); });
  if (sn) NIVELES.forEach(function(n){ var o=document.createElement('option'); o.value=n; o.textContent=n; sn.appendChild(o); });
}

async function actualizarIPsBloqueadas() {
  var data  = await fetchJSON('/ips/bloqueadas');
  var lista = document.getElementById('lista-ips');
  if (!lista) return;
  if (!data || data.length === 0) { lista.innerHTML = '<div class="ips-empty">Sin IPs bloqueadas</div>'; return; }

  var mOpts = MOTIVOS.map(function(m){ return '<option value="'+m+'">'+m+'</option>'; }).join('');
  var nOpts = NIVELES.map(function(n){ return '<option value="'+n+'">'+n+'</option>'; }).join('');

  var html = '';
  data.forEach(function(item) {
    var key   = item.ip.replace(/\./g,'-');
    var nCls  = item.nivel==='ALTO'?'nivel-alto':item.nivel==='MEDIO'?'nivel-medio':'nivel-bajo';
    var mO    = mOpts.replace('value="'+item.motivo+'"','value="'+item.motivo+'" selected');
    var nO    = nOpts.replace('value="'+item.nivel+'"','value="'+item.nivel+'" selected');
    html +=
      '<div class="ip-row" id="row-'+key+'">' +
        '<div class="ip-info">' +
          '<div class="ip-addr">'+item.ip+' <span class="nivel-badge '+nCls+'">'+item.nivel+'</span>' +
          ' <span class="intentos-badge">'+item.intentos+' intentos</span></div>' +
          '<div class="ip-meta">'+item.bloqueada_en+'</div>' +
        '</div>' +
        '<div class="ip-editar">' +
          '<select class="ip-select" id="motivo-'+key+'">'+mO+'</select>' +
          '<select class="ip-select" id="nivel-'+key+'">'+nO+'</select>' +
          '<button class="btn-guardar" onclick="editarIP(\''+item.ip+'\')">Guardar</button>' +
          '<button class="btn-desbloquear" onclick="desbloquearIP(\''+item.ip+'\')">Eliminar</button>' +
        '</div>' +
      '</div>';
  });
  lista.innerHTML = html;
}

function bloquearIPManual() {
  var iEl = document.getElementById('input-ip-bloquear');
  var mEl = document.getElementById('select-motivo-nuevo');
  var nEl = document.getElementById('select-nivel-nuevo');
  var ip  = (iEl ? iEl.value : '').trim();
  if (!ip) { alert('Ingresa una IP'); return; }
  fetch('/ips/bloquear', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ ip:ip, motivo:mEl?mEl.value:'Actividad sospechosa', nivel:nEl?nEl.value:'BAJO' }) })
  .then(function(){ if(iEl) iEl.value=''; actualizarIPsBloqueadas(); actualizarTopIPs(); })
  .catch(function(e){ console.error(e); });
}

function editarIP(ip) {
  var key = ip.replace(/\./g,'-');
  var m   = document.getElementById('motivo-'+key);
  var n   = document.getElementById('nivel-'+key);
  if (!m||!n) return;
  fetch('/ips/editar/'+encodeURIComponent(ip), { method:'PUT', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ motivo:m.value, nivel:n.value }) })
  .then(function(){ actualizarIPsBloqueadas(); })
  .catch(function(e){ console.error(e); });
}

function desbloquearIP(ip) {
  fetch('/ips/desbloquear/'+encodeURIComponent(ip), { method:'DELETE' })
  .then(function(){ actualizarIPsBloqueadas(); actualizarHistorial(); actualizarTopIPs(); })
  .catch(function(e){ console.error(e); });
}

async function actualizarHistorial() {
  var data  = await fetchJSON('/ips/historial');
  var lista = document.getElementById('historial-lista');
  if (!lista) return;
  if (!data||data.length===0) { lista.innerHTML='<div class="ips-empty">Sin intentos registrados</div>'; return; }
  var html='';
  data.forEach(function(item){
    var mc='m-'+(item.metodo||'get').toLowerCase();
    html+='<div class="historial-item">' +
      '<span class="hist-ts">'+item.ts+'</span>' +
      '<span class="hist-ip">'+item.ip+'</span>' +
      '<span class="feed-metodo '+mc+'" style="font-size:10px">'+item.metodo+'</span>' +
      '<span class="hist-endpoint">'+item.endpoint+'</span></div>';
  });
  lista.innerHTML=html;
}

// ─── Alertas ──────────────────────────────────────────────────────────────────

async function verificarAlertas() {
  var kpis = await fetchJSON('/stats/kpis');
  var bT   = document.getElementById('alerta-tasa');
  var bL   = document.getElementById('alerta-latencia');
  var vT   = document.getElementById('val-tasa');
  var vL   = document.getElementById('val-lat');
  if (!bT||!bL) return;
  if (kpis.tasa_error>10){ bT.style.display='flex'; if(vT) vT.textContent=kpis.tasa_error+'%'; }
  else bT.style.display='none';
  if (kpis.latencia>800) { bL.style.display='flex'; if(vL) vL.textContent=kpis.latencia+'ms'; }
  else bL.style.display='none';
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
      actualizarCodigos(),
      actualizarMetodos(),
      actualizarTasaEndpoint(),
      actualizarLatenciaHora(),
      actualizarCruce(),
      actualizarRPM(),
      actualizarDisponibilidad(),
      actualizarHeatmap(),
      actualizarTopIPs(),
      actualizarTabla(),
      actualizarIPsBloqueadas(),
      actualizarHistorial(),
      verificarAlertas(),
    ]);
    actualizarTimestamp();
  } catch(err) {
    console.error('Error:', err);
    document.getElementById('last-update').textContent = 'error de conexion';
  }
}

// ─── Arranque ─────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
  initCharts();
  cargarOpciones().then(function() {
    refreshAll();
    setInterval(refreshAll, 3000);
  });
});