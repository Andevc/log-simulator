"""
app.py - Dashboard de analisis de logs en tiempo real.
Sirve el frontend estatico y expone 6 endpoints REST que consultan Cassandra.

Uso:
    python app.py

Luego abrir: http://localhost:5000
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

from cassandra.cluster import Cluster
from cassandra.policies import RoundRobinPolicy
from flask import Flask, jsonify, send_from_directory


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


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("Dashboard disponible en: http://localhost:5000")
    print("Presiona Ctrl+C para detener.")
    print()
    app.run(host="0.0.0.0", port=5000, debug=False)
