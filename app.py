from __future__ import annotations

import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

from cassandra.cluster import Cluster # type: ignore
from cassandra.policies import RoundRobinPolicy # type: ignore
from flask import Flask, jsonify, request, send_from_directory


# ─── Configuracion ────────────────────────────────────────────────────────────

CASSANDRA_HOST = "127.0.0.1"
CASSANDRA_PORT = 9042
KEYSPACE       = "log_simulator"

ENDPOINTS_CONOCIDOS = [
    "/api/users",
    "/api/products",
    "/api/orders",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/search",
    "/api/cart",
    "/api/payments",
    "/api/reports",
    "/healthcheck",
]


# ─── Conexion global ──────────────────────────────────────────────────────────

def conectar_cassandra():
    """Retorna una sesion de Cassandra. Termina el proceso si falla."""
    try:
        cluster = Cluster(
            [CASSANDRA_HOST],
            port=CASSANDRA_PORT,
            load_balancing_policy=RoundRobinPolicy(),
            protocol_version=4,
        )
        session = cluster.connect(KEYSPACE)
        print("Cassandra conectada OK")
        return session
    except Exception as exc:
        print("ERROR al conectar a Cassandra:", exc)
        print("Asegurate de haber ejecutado setup_db.py y generator.py primero.")
        sys.exit(1)


app     = Flask(__name__, static_folder="static")
session = conectar_cassandra()  # sesion compartida por todos los endpoints


# ─── Helpers ──────────────────────────────────────────────────────────────────

def ultimas_24h():
    """Retorna lista de (fecha_date, hora_int) de las ultimas 24 horas."""
    ahora    = datetime.utcnow()
    hace_24h = ahora - timedelta(hours=24)
    puntos   = []
    cursor   = hace_24h.replace(minute=0, second=0, microsecond=0)
    while cursor <= ahora:
        puntos.append((cursor.date(), cursor.hour))
        cursor += timedelta(hours=1)
    return puntos


# ─── Rutas estaticas ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/usuario")
def usuario():
    return send_from_directory("static", "usuario.html")


# ─── KPIs generales ───────────────────────────────────────────────────────────

@app.route("/stats/kpis")
def kpis():
    """
    Retorna:
      total      - total de requests en las ultimas 24h
      errores    - cantidad de errores HTTP 5xx
      tasa_error - porcentaje de errores
      latencia   - latencia promedio global (ms)
    """
    total      = 0
    errores    = 0
    suma_lat   = 0
    cant_lat   = 0

    puntos = ultimas_24h()
    for fecha, hora in puntos:
        rows = session.execute(
            "SELECT codigo_http, latencia_ms FROM logs_por_hora WHERE fecha=%s AND hora=%s",
            (fecha, hora),
        )
        for row in rows:
            total += 1
            suma_lat += row.latencia_ms
            cant_lat += 1
            if row.codigo_http >= 500:
                errores += 1

    tasa_error = round((errores / total * 100), 2) if total > 0 else 0
    latencia   = round(suma_lat / cant_lat, 1)     if cant_lat > 0 else 0

    return jsonify({
        "total":      total,
        "errores":    errores,
        "tasa_error": tasa_error,
        "latencia":   latencia,
    })


# ─── Trafico por hora ─────────────────────────────────────────────────────────

@app.route("/stats/trafico")
def trafico():
    """
    Retorna lista de {hora, requests} para las ultimas 24 horas.
    Usada por la grafica de linea del dashboard.
    """
    resultado: Dict[str, int] = {}

    puntos = ultimas_24h()
    for fecha, hora in puntos:
        rows = session.execute(
            "SELECT count(*) FROM logs_por_hora WHERE fecha=%s AND hora=%s",
            (fecha, hora),
        )
        cantidad = rows.one().count if rows else 0
        etiqueta = "{:02d}:00".format(hora)
        resultado[etiqueta] = int(cantidad)

    return jsonify([
        {"hora": k, "requests": v}
        for k, v in resultado.items()
    ])


# ─── Errores 5xx por hora ─────────────────────────────────────────────────────

@app.route("/stats/errores")
def errores_por_hora():
    """
    Retorna lista de {hora, errores} — solo conteo de HTTP 5xx.
    """
    resultado: Dict[str, int] = defaultdict(int)

    puntos = ultimas_24h()
    for fecha, hora in puntos:
        rows = session.execute(
            "SELECT codigo_http FROM logs_por_hora WHERE fecha=%s AND hora=%s",
            (fecha, hora),
        )
        etiqueta = "{:02d}:00".format(hora)
        for row in rows:
            if row.codigo_http >= 500:
                resultado[etiqueta] += 1

    return jsonify([
        {"hora": k, "errores": v}
        for k, v in sorted(resultado.items())
    ])


# ─── Latencia promedio por endpoint ──────────────────────────────────────────

@app.route("/stats/latencia")
def latencia_por_endpoint():
    """
    Retorna lista de {endpoint, latencia_promedio} para los 10 endpoints.
    Consulta logs_por_endpoint (particion por endpoint).
    """
    resultado: List[Dict[str, Any]] = []

    for ep in ENDPOINTS_CONOCIDOS:
        rows = session.execute(
            "SELECT latencia_ms FROM logs_por_endpoint WHERE endpoint=%s LIMIT 5000",
            (ep,),
        )
        valores = [row.latencia_ms for row in rows]
        promedio = round(sum(valores) / len(valores), 1) if valores else 0
        resultado.append({"endpoint": ep, "latencia_promedio": promedio})

    resultado.sort(key=lambda x: x["latencia_promedio"], reverse=True)
    return jsonify(resultado)


# ─── Top endpoints por trafico ────────────────────────────────────────────────

@app.route("/stats/top-endpoints")
def top_endpoints():
    """
    Retorna lista de {endpoint, total} ordenados por volumen de requests.
    """
    conteos: Dict[str, int] = {}

    for ep in ENDPOINTS_CONOCIDOS:
        rows = session.execute(
            "SELECT count(*) FROM logs_por_endpoint WHERE endpoint=%s",
            (ep,),
        )
        conteos[ep] = int(rows.one().count) if rows else 0

    ordenados = sorted(conteos.items(), key=lambda x: x[1], reverse=True)
    return jsonify([
        {"endpoint": k, "total": v}
        for k, v in ordenados
    ])


# ─── Logs recientes ───────────────────────────────────────────────────────────

@app.route("/logs/recientes")
def logs_recientes():
    """
    Retorna los ultimos 50 logs del endpoint mas activo.
    Muestra en la tabla en vivo del dashboard.
    """
    todos: List[Dict[str, Any]] = []

    for ep in ENDPOINTS_CONOCIDOS:
        rows = session.execute(
            """
            SELECT endpoint, ts, ip_cliente, metodo, codigo_http, latencia_ms
            FROM logs_por_endpoint
            WHERE endpoint=%s
            LIMIT 10
            """,
            (ep,),
        )
        for row in rows:
            todos.append({
                "endpoint":    row.endpoint,
                "timestamp":   row.ts.strftime("%H:%M:%S") if row.ts else "",
                "ip":          row.ip_cliente,
                "metodo":      row.metodo,
                "codigo":      row.codigo_http,
                "latencia_ms": row.latencia_ms,
            })

    # Ordenar por timestamp descendente y tomar los 50 mas recientes
    todos.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify(todos[:50])


# ─── Accion de usuario (simulador) ───────────────────────────────────────────

@app.route("/accion", methods=["POST"])
def accion_usuario():
    """
    Recibe un click del simulador de usuario.
    Verifica si la IP esta bloqueada antes de insertar el log.
    Body JSON: { ip, endpoint, metodo }
    """
    import random
    data     = request.get_json(silent=True) or {}
    ip       = data.get("ip", "192.168.1.1")
    endpoint = data.get("endpoint", "/api/users")
    metodo   = data.get("metodo", "GET")

    # Verificar si la IP esta bloqueada
    row = session.execute(
        "SELECT ip FROM ips_bloqueadas WHERE ip=%s", (ip,)
    ).one()

    if row:
        # Registrar intento en historial e incrementar contador
        session.execute(
            "INSERT INTO intentos_bloqueados (ip, ts, endpoint, metodo) VALUES (%s, %s, %s, %s)",
            (ip, datetime.utcnow(), endpoint, metodo)
        )
        session.execute(
            "UPDATE ips_bloqueadas SET intentos = intentos + 1 WHERE ip=%s", (ip,)
        )
        return jsonify({"bloqueada": True, "mensaje": "IP bloqueada — acceso denegado"}), 403
    
    # Generar el log
    ahora   = datetime.utcnow()
    log_id  = uuid.uuid4()
    codigo  = random.choices(
        [200, 200, 200, 201, 400, 404, 500, 503],
        weights=[40, 15, 15, 10, 8, 6, 4, 2],
        k=1
    )[0]

    if codigo >= 500:
        latencia = random.randint(800, 3000)
    elif codigo >= 400:
        latencia = random.randint(200, 800)
    else:
        latencia = random.randint(20, 300)

    # Doble-write
    session.execute(
        """INSERT INTO logs_por_hora
           (fecha, hora, log_id, ip_cliente, endpoint, metodo, codigo_http, latencia_ms, ts)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (ahora.date(), ahora.hour, log_id, ip, endpoint, metodo, codigo, latencia, ahora)
    )
    session.execute(
        """INSERT INTO logs_por_endpoint
           (endpoint, ts, log_id, ip_cliente, metodo, codigo_http, latencia_ms)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (endpoint, ahora, log_id, ip, metodo, codigo, latencia)
    )

    return jsonify({
        "bloqueada":   False,
        "codigo":      codigo,
        "latencia_ms": latencia,
        "timestamp":   ahora.strftime("%H:%M:%S"),
    })


# ─── CRUD IPs bloqueadas ──────────────────────────────────────────────────────

# ─── CRUD IPs bloqueadas ──────────────────────────────────────────────────────

MOTIVOS_VALIDOS = [
    "Actividad sospechosa",
    "Demasiados errores 500",
    "Fuerza bruta detectada",
    "IP desconocida",
    "Acceso no autorizado",
    "Mantenimiento",
]

NIVELES_VALIDOS = ["BAJO", "MEDIO", "ALTO"]


@app.route("/ips/bloqueadas", methods=["GET"])
def listar_ips():
    rows = session.execute("SELECT ip, motivo, nivel, bloqueada_en, intentos FROM ips_bloqueadas")
    resultado = []
    for row in rows:
        ts = row.bloqueada_en.timestamp() if row.bloqueada_en else -1
        resultado.append({
            "ip":          row.ip,
            "motivo":      row.motivo or "Actividad sospechosa",
            "nivel":       row.nivel  or "BAJO",
            "intentos":    row.intentos or 0,
            "bloqueada_en": row.bloqueada_en.strftime("%H:%M:%S %d/%m/%Y") if row.bloqueada_en else "",
            "_ts": ts,
        })

    resultado.sort(key=lambda x: x["_ts"], reverse=True)
    for item in resultado:
        item.pop("_ts", None)

    return jsonify(resultado)


@app.route("/ips/bloquear", methods=["POST"])
def bloquear_ip():
    data   = request.get_json(silent=True) or {}
    ip     = data.get("ip", "").strip()
    motivo = data.get("motivo", "Actividad sospechosa").strip()
    nivel  = data.get("nivel", "BAJO").strip().upper()

    if not ip:
        return jsonify({"error": "IP requerida"}), 400
    if motivo not in MOTIVOS_VALIDOS:
        motivo = MOTIVOS_VALIDOS[0]
    if nivel not in NIVELES_VALIDOS:
        nivel = "BAJO"

    session.execute(
        "INSERT INTO ips_bloqueadas (ip, motivo, nivel, bloqueada_en, intentos) VALUES (%s, %s, %s, %s, %s)",
        (ip, motivo, nivel, datetime.utcnow(), 0)
    )
    return jsonify({"ok": True, "ip": ip, "motivo": motivo, "nivel": nivel})


@app.route("/ips/editar/<ip>", methods=["PUT"])
def editar_ip(ip):
    """Actualiza motivo y/o nivel de una IP bloqueada."""
    data   = request.get_json(silent=True) or {}
    motivo = data.get("motivo", "").strip()
    nivel  = data.get("nivel", "").strip().upper()

    if motivo not in MOTIVOS_VALIDOS:
        return jsonify({"error": "Motivo no valido"}), 400
    if nivel not in NIVELES_VALIDOS:
        return jsonify({"error": "Nivel no valido"}), 400

    session.execute(
        "UPDATE ips_bloqueadas SET motivo=%s, nivel=%s WHERE ip=%s",
        (motivo, nivel, ip)
    )
    return jsonify({"ok": True, "ip": ip, "motivo": motivo, "nivel": nivel})


@app.route("/ips/desbloquear/<ip>", methods=["DELETE"])
def desbloquear_ip(ip):
    session.execute("DELETE FROM ips_bloqueadas WHERE ip=%s", (ip,))
    return jsonify({"ok": True, "ip": ip})


@app.route("/ips/intento", methods=["POST"])
def registrar_intento():
    """Registra un intento de acceso de una IP bloqueada e incrementa su contador."""
    data     = request.get_json(silent=True) or {}
    ip       = data.get("ip", "")
    endpoint = data.get("endpoint", "")
    metodo   = data.get("metodo", "GET")

    # Registrar en historial
    session.execute(
        "INSERT INTO intentos_bloqueados (ip, ts, endpoint, metodo) VALUES (%s, %s, %s, %s)",
        (ip, datetime.utcnow(), endpoint, metodo)
    )
    # Incrementar contador (UPDATE en Cassandra)
    session.execute(
        "UPDATE ips_bloqueadas SET intentos = intentos + 1 WHERE ip=%s", (ip,)
    )
    return jsonify({"ok": True})


@app.route("/ips/historial", methods=["GET"])
def historial_intentos():
    """Retorna los ultimos intentos de acceso bloqueados."""
    ip = request.args.get("ip", None)
    todos = []

    if ip:
        rows = session.execute(
            "SELECT ip, ts, endpoint, metodo FROM intentos_bloqueados WHERE ip=%s LIMIT 20", (ip,)
        )
    else:
        # Sin ip: traer de todas las IPs bloqueadas actuales
        ips_rows = session.execute("SELECT ip FROM ips_bloqueadas")
        rows = []
        for r in ips_rows:
            sub = session.execute(
                "SELECT ip, ts, endpoint, metodo FROM intentos_bloqueados WHERE ip=%s LIMIT 5", (r.ip,)
            )
            rows.extend(sub)

    for row in rows:
        todos.append({
            "ip":       row.ip,
            "ts":       row.ts.strftime("%H:%M:%S") if row.ts else "",
            "endpoint": row.endpoint,
            "metodo":   row.metodo,
        })

    todos.sort(key=lambda x: x["ts"], reverse=True)
    return jsonify(todos[:30])


@app.route("/ips/motivos", methods=["GET"])
def motivos():
    """Retorna las listas de motivos y niveles validos para los dropdowns."""
    return jsonify({"motivos": MOTIVOS_VALIDOS, "niveles": NIVELES_VALIDOS})


# ─── Distribucion de codigos HTTP ────────────────────────────────────────────

@app.route("/stats/codigos")
def distribucion_codigos():
    """
    Retorna conteo de cada codigo HTTP en las ultimas 24h.
    Usado por la grafica de dona de codigos HTTP.
    """
    conteos: Dict[int, int] = defaultdict(int)

    puntos = ultimas_24h()
    for fecha, hora in puntos:
        rows = session.execute(
            "SELECT codigo_http FROM logs_por_hora WHERE fecha=%s AND hora=%s",
            (fecha, hora),
        )
        for row in rows:
            conteos[row.codigo_http] += 1

    return jsonify([
        {"codigo": k, "total": v}
        for k, v in sorted(conteos.items())
    ])


# ─── Distribucion de metodos HTTP ─────────────────────────────────────────────

@app.route("/stats/metodos")
def distribucion_metodos():
    """
    Retorna conteo de cada metodo HTTP en las ultimas 24h.
    Usado por la grafica de dona de metodos HTTP.
    """
    conteos: Dict[str, int] = defaultdict(int)

    puntos = ultimas_24h()
    for fecha, hora in puntos:
        rows = session.execute(
            "SELECT metodo FROM logs_por_hora WHERE fecha=%s AND hora=%s",
            (fecha, hora),
        )
        for row in rows:
            conteos[row.metodo] += 1

    return jsonify([
        {"metodo": k, "total": v}
        for k, v in sorted(conteos.items(), key=lambda x: x[1], reverse=True)
    ])


# ─── Tasa de error por endpoint ───────────────────────────────────────────────

@app.route("/stats/tasa-error-endpoint")
def tasa_error_endpoint():
    """
    Retorna tasa de error (%) por endpoint.
    Usado por la grafica de barras horizontales de tasa de error.
    """
    resultado: List[Dict[str, Any]] = []

    for ep in ENDPOINTS_CONOCIDOS:
        rows = session.execute(
            "SELECT codigo_http FROM logs_por_endpoint WHERE endpoint=%s LIMIT 5000",
            (ep,),
        )
        total  = 0
        errores = 0
        for row in rows:
            total += 1
            if row.codigo_http >= 400:
                errores += 1

        tasa = round((errores / total * 100), 1) if total > 0 else 0
        resultado.append({"endpoint": ep, "tasa_error": tasa, "total": total})

    resultado.sort(key=lambda x: x["tasa_error"], reverse=True)
    return jsonify(resultado)


# ─── Latencia promedio por hora ───────────────────────────────────────────────

@app.route("/stats/latencia-hora")
def latencia_por_hora():
    """
    Retorna latencia promedio por hora en las ultimas 24h.
    Usado por la grafica de linea de evolucion de latencia.
    """
    resultado: Dict[str, Any] = {}

    puntos = ultimas_24h()
    for fecha, hora in puntos:
        rows = session.execute(
            "SELECT latencia_ms FROM logs_por_hora WHERE fecha=%s AND hora=%s",
            (fecha, hora),
        )
        valores = [row.latencia_ms for row in rows]
        promedio = round(sum(valores) / len(valores), 1) if valores else 0
        etiqueta = "{:02d}:00".format(hora)
        resultado[etiqueta] = promedio

    return jsonify([
        {"hora": k, "latencia": v}
        for k, v in resultado.items()
    ])


# ─── Percentil de latencia P95 / P99 ─────────────────────────────────────────

@app.route("/stats/percentiles")
def percentiles_latencia():
    """
    Retorna P50, P95 y P99 de latencia por endpoint.
    Detecta picos que el promedio oculta.
    """
    import math
    resultado: List[Dict[str, Any]] = []

    for ep in ENDPOINTS_CONOCIDOS:
        rows = session.execute(
            "SELECT latencia_ms FROM logs_por_endpoint WHERE endpoint=%s LIMIT 5000",
            (ep,),
        )
        valores = sorted([row.latencia_ms for row in rows])
        if not valores:
            resultado.append({"endpoint": ep, "p50": 0, "p95": 0, "p99": 0})
            continue

        def percentil(datos, p):
            idx = int(math.ceil(len(datos) * p / 100.0)) - 1
            return datos[max(0, min(idx, len(datos) - 1))]

        resultado.append({
            "endpoint": ep,
            "p50": percentil(valores, 50),
            "p95": percentil(valores, 95),
            "p99": percentil(valores, 99),
        })

    resultado.sort(key=lambda x: x["p95"], reverse=True)
    return jsonify(resultado)


# ─── Requests por minuto (RPM) ────────────────────────────────────────────────

@app.route("/stats/rpm")
def requests_por_minuto():
    """
    Retorna el RPM de los ultimos 5 minutos.
    """
    ahora     = datetime.utcnow()
    hace_5min = ahora - timedelta(minutes=5)

    total = 0
    # Consultar la hora actual y la anterior por si el rango cruza la hora
    for delta in [0, 1]:
        t      = ahora - timedelta(hours=delta)
        fecha  = t.date()
        hora   = t.hour
        rows   = session.execute(
            "SELECT ts FROM logs_por_hora WHERE fecha=%s AND hora=%s",
            (fecha, hora),
        )
        for row in rows:
            if row.ts and row.ts.replace(tzinfo=None) >= hace_5min:
                total += 1

    rpm = round(total / 5.0, 1)
    return jsonify({"rpm": rpm, "total_5min": total})


# ─── Mapa de calor hora vs trafico ────────────────────────────────────────────

@app.route("/stats/heatmap")
def heatmap():
    """
    Retorna matriz de trafico: para cada hora del dia (0-23)
    retorna el conteo de requests. Usado por el mapa de calor.
    """
    conteos: Dict[int, int] = defaultdict(int)

    puntos = ultimas_24h()
    for fecha, hora in puntos:
        rows = session.execute(
            "SELECT count(*) FROM logs_por_hora WHERE fecha=%s AND hora=%s",
            (fecha, hora),
        )
        cantidad = rows.one().count if rows else 0
        conteos[hora] += int(cantidad)

    return jsonify([
        {"hora": h, "total": conteos.get(h, 0)}
        for h in range(24)
    ])


# ─── Scatter: latencia vs volumen por endpoint ────────────────────────────────

@app.route("/stats/scatter")
def scatter_latencia_volumen():
    """
    Retorna por endpoint: total de requests y latencia promedio.
    Usado por el scatter plot latencia vs volumen.
    """
    resultado: List[Dict[str, Any]] = []

    for ep in ENDPOINTS_CONOCIDOS:
        rows = session.execute(
            "SELECT latencia_ms FROM logs_por_endpoint WHERE endpoint=%s LIMIT 5000",
            (ep,),
        )
        valores = [row.latencia_ms for row in rows]
        if not valores:
            continue
        resultado.append({
            "endpoint":  ep,
            "volumen":   len(valores),
            "latencia":  round(sum(valores) / len(valores), 1),
        })

    return jsonify(resultado)


# ─── Ratio de disponibilidad (uptime) ────────────────────────────────────────

@app.route("/stats/disponibilidad")
def disponibilidad():
    """
    Retorna porcentaje de requests exitosos (2xx) vs total.
    """
    total    = 0
    exitosos = 0

    puntos = ultimas_24h()
    for fecha, hora in puntos:
        rows = session.execute(
            "SELECT codigo_http FROM logs_por_hora WHERE fecha=%s AND hora=%s",
            (fecha, hora),
        )
        for row in rows:
            total += 1
            if 200 <= row.codigo_http < 300:
                exitosos += 1

    ratio = round((exitosos / total * 100), 2) if total > 0 else 0
    return jsonify({
        "ratio":    ratio,
        "exitosos": exitosos,
        "total":    total,
        "fallidos": total - exitosos,
    })


# ─── Top IPs por volumen de requests ─────────────────────────────────────────

@app.route("/stats/top-ips")
def top_ips():
    """
    Retorna las 10 IPs con mas requests en las ultimas 24h.
    """
    conteos: Dict[str, int] = defaultdict(int)

    puntos = ultimas_24h()
    for fecha, hora in puntos:
        rows = session.execute(
            "SELECT ip_cliente FROM logs_por_hora WHERE fecha=%s AND hora=%s",
            (fecha, hora),
        )
        for row in rows:
            conteos[row.ip_cliente] += 1

    ordenadas = sorted(conteos.items(), key=lambda x: x[1], reverse=True)[:10]

    # Marcar si la IP esta bloqueada
    ips_bloqueadas_rows = session.execute("SELECT ip FROM ips_bloqueadas")
    bloqueadas          = {r.ip for r in ips_bloqueadas_rows}

    return jsonify([
        {
            "ip":        ip,
            "total":     total,
            "bloqueada": ip in bloqueadas,
        }
        for ip, total in ordenadas
    ])


# ─── Cruce de tablas: trafico vs errores por endpoint ─────────────────────────

@app.route("/stats/cruce")
def cruce_tablas():
    """
    Combina datos de logs_por_endpoint (volumen total) y logs_por_hora (errores 5xx).
    Demuestra el patron doble-write: mismos datos, dos tablas, dos consultas distintas.
    """
    # TABLA 1: logs_por_endpoint -> volumen total por endpoint
    volumen: Dict[str, int] = {}
    for ep in ENDPOINTS_CONOCIDOS:
        rows = session.execute(
            "SELECT count(*) FROM logs_por_endpoint WHERE endpoint=%s", (ep,)
        )
        volumen[ep] = int(rows.one().count) if rows else 0

    # TABLA 2: logs_por_hora -> errores 5xx por endpoint en las ultimas 24h
    errores_ep: Dict[str, int] = defaultdict(int)
    puntos = ultimas_24h()
    for fecha, hora in puntos:
        rows = session.execute(
            "SELECT endpoint, codigo_http FROM logs_por_hora WHERE fecha=%s AND hora=%s",
            (fecha, hora),
        )
        for row in rows:
            if row.codigo_http >= 500:
                errores_ep[row.endpoint] += 1

    # Combinar ambas fuentes
    resultado = []
    for ep in ENDPOINTS_CONOCIDOS:
        resultado.append({
            "endpoint": ep,
            "volumen":  volumen.get(ep, 0),
            "errores":  errores_ep.get(ep, 0),
        })

    resultado.sort(key=lambda x: x["volumen"], reverse=True)
    return jsonify(resultado)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("Dashboard disponible en: http://localhost:5000")
    print("Presiona Ctrl+C para detener.")
    print()
    app.run(host="0.0.0.0", port=5000, debug=False)