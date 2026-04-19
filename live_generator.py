"""
live_generator.py - Genera logs continuamente en tiempo real.
Usar durante la exposicion para que el dashboard muestre datos actualizandose en vivo.

Uso (en una terminal separada mientras app.py corre):
    python live_generator.py

Presiona Ctrl+C para detener.
"""

from __future__ import annotations

import random
import sys
import time
import uuid
from datetime import datetime

from cassandra.cluster import Cluster
from cassandra.policies import RoundRobinPolicy
from faker import Faker


# ─── Configuracion ────────────────────────────────────────────────────────────

CASSANDRA_HOST    = "127.0.0.1"
CASSANDRA_PORT    = 9042
KEYSPACE          = "log_simulator"

REGISTROS_POR_LOTE = 15       # logs por rafaga
PAUSA_SEGUNDOS     = 2        # segundos entre rafagas

ENDPOINTS = [
    ("/api/users",       20),
    ("/api/products",    18),
    ("/api/orders",      15),
    ("/api/auth/login",  12),
    ("/api/auth/logout",  5),
    ("/api/search",      14),
    ("/api/cart",         8),
    ("/api/payments",     5),
    ("/api/reports",      2),
    ("/healthcheck",      1),
]

ENDPOINT_NAMES = [e[0] for e in ENDPOINTS]
ENDPOINT_PESOS = [e[1] for e in ENDPOINTS]
METODOS        = ["GET", "GET", "GET", "POST", "PUT", "DELETE"]
CODIGOS        = [200, 200, 200, 200, 201, 301, 400, 401, 404, 404, 500, 503]


# ─── Conexion ─────────────────────────────────────────────────────────────────

def conectar():
    print("Conectando a Cassandra...", end=" ", flush=True)
    try:
        cluster = Cluster(
            [CASSANDRA_HOST],
            port=CASSANDRA_PORT,
            load_balancing_policy=RoundRobinPolicy(),
            protocol_version=4,
        )
        session = cluster.connect(KEYSPACE)
        print("OK")
        return cluster, session
    except Exception as exc:
        print("\nERROR:", exc)
        print("Asegurate de que app.py y Cassandra esten corriendo.")
        sys.exit(1)


# ─── Generacion e insercion ───────────────────────────────────────────────────

def insertar_log(session, stmt_hora, stmt_endpoint, fake):
    ahora    = datetime.utcnow()
    log_id   = uuid.uuid4()
    endpoint = random.choices(ENDPOINT_NAMES, weights=ENDPOINT_PESOS, k=1)[0]
    metodo   = random.choice(METODOS)
    codigo   = random.choice(CODIGOS)
    ip       = fake.ipv4()

    if codigo >= 500:
        latencia = random.randint(800, 4000)
    elif codigo >= 400:
        latencia = random.randint(200, 800)
    else:
        latencia = random.randint(10, 350)

    session.execute(stmt_hora, (
        ahora.date(), ahora.hour, log_id,
        ip, endpoint, metodo, codigo, latencia, ahora
    ))
    session.execute(stmt_endpoint, (
        endpoint, ahora, log_id,
        ip, metodo, codigo, latencia
    ))

    return endpoint, metodo, codigo, latencia


def preparar_statements(session):
    stmt_hora = session.prepare("""
        INSERT INTO logs_por_hora
            (fecha, hora, log_id, ip_cliente, endpoint, metodo, codigo_http, latencia_ms, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """)
    stmt_endpoint = session.prepare("""
        INSERT INTO logs_por_endpoint
            (endpoint, ts, log_id, ip_cliente, metodo, codigo_http, latencia_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """)
    return stmt_hora, stmt_endpoint


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    fake = Faker()
    cluster, session = conectar()
    stmt_hora, stmt_endpoint = preparar_statements(session)

    total    = 0
    errores  = 0
    inicio   = time.time()

    print()
    print("Generando {} logs cada {}s — el dashboard se actualiza en vivo.".format(
        REGISTROS_POR_LOTE, PAUSA_SEGUNDOS
    ))
    print("Presiona Ctrl+C para detener.")
    print()
    print("{:<8} {:<6} {:<22} {:<7} {:<6}".format(
        "HORA", "METODO", "ENDPOINT", "CODIGO", "LAT(ms)"
    ))
    print("-" * 58)

    try:
        while True:
            lote_errores = 0
            for _ in range(REGISTROS_POR_LOTE):
                try:
                    endpoint, metodo, codigo, latencia = insertar_log(
                        session, stmt_hora, stmt_endpoint, fake
                    )
                    total += 1
                    if codigo >= 500:
                        errores     += 1
                        lote_errores += 1

                    # Mostrar solo algunos logs en consola para no saturar
                    if total % 3 == 0:
                        ts = datetime.utcnow().strftime("%H:%M:%S")
                        marca = " ← ERROR" if codigo >= 500 else ""
                        print("{:<8} {:<6} {:<22} {:<7} {:<6}{}".format(
                            ts, metodo, endpoint, codigo, latencia, marca
                        ))
                except Exception as exc:
                    print("  [WARN] Error al insertar:", exc)

            # Resumen del lote
            elapsed = time.time() - inicio
            print("  → Lote insertado | Total: {:,} | Errores acum.: {:,} | Tiempo: {:.0f}s".format(
                total, errores, elapsed
            ))
            print()

            time.sleep(PAUSA_SEGUNDOS)

    except KeyboardInterrupt:
        elapsed = time.time() - inicio
        print()
        print("=" * 50)
        print("Generador detenido.")
        print("  Insertados : {:,}".format(total))
        print("  Errores    : {:,}".format(errores))
        print("  Tiempo     : {:.1f}s".format(elapsed))
        print("=" * 50)
        cluster.shutdown()


if __name__ == "__main__":
    main()
