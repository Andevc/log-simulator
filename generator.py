from __future__ import annotations

import random
import sys
import time
import uuid
from datetime import datetime, timedelta

from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args
from cassandra.policies import RoundRobinPolicy
from faker import Faker


# ─── Configuracion ────────────────────────────────────────────────────────────

CASSANDRA_HOST  = "127.0.0.1"
CASSANDRA_PORT  = 9042
KEYSPACE        = "log_simulator"
TOTAL_REGISTROS = 20_000
BATCH_SIZE      = 200          # registros por lote de insercion
CONCURRENCIA    = 50           # peticiones paralelas a Cassandra

ENDPOINTS = [
    ("/api/users",          20),
    ("/api/products",       18),
    ("/api/orders",         15),
    ("/api/auth/login",     12),
    ("/api/auth/logout",     5),
    ("/api/search",         14),
    ("/api/cart",            8),
    ("/api/payments",        5),
    ("/api/reports",         2),
    ("/healthcheck",         1),
]

ENDPOINT_NAMES  = [e[0] for e in ENDPOINTS]
ENDPOINT_PESOS  = [e[1] for e in ENDPOINTS]

METODOS = ["GET", "GET", "GET", "POST", "PUT", "DELETE"]  # GET mas frecuente

# Codigos HTTP con distribucion realista
CODIGOS = [200, 200, 200, 200, 200, 201, 301, 400, 401, 403, 404, 404, 500, 503]

# Ventana de tiempo simulada: ultimas 24 horas
AHORA     = datetime.utcnow()
HACE_24H  = AHORA - timedelta(hours=24)


# ─── Conexion ─────────────────────────────────────────────────────────────────

def conectar() -> tuple:
    """Conecta a Cassandra y retorna (cluster, session)."""
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
        print("Asegurate de haber ejecutado: python setup_db.py")
        sys.exit(1)


# ─── Generacion de datos ──────────────────────────────────────────────────────

def generar_timestamp() -> datetime:
    """Retorna un timestamp aleatorio dentro de las ultimas 24 horas."""
    offset_segundos = random.randint(0, 86_400)
    return HACE_24H + timedelta(seconds=offset_segundos)


def generar_log(fake: Faker) -> dict:
    """Genera un registro de log con datos realistas."""
    ts       = generar_timestamp()
    endpoint = random.choices(ENDPOINT_NAMES, weights=ENDPOINT_PESOS, k=1)[0]
    codigo   = random.choice(CODIGOS)

    # Latencia mas alta para errores 5xx
    if codigo >= 500:
        latencia = random.randint(800, 5_000)
    elif codigo >= 400:
        latencia = random.randint(200, 800)
    else:
        latencia = random.randint(10, 400)

    return {
        "log_id":      uuid.uuid4(),
        "ts":          ts,
        "fecha":       ts.date(),
        "hora":        ts.hour,
        "ip_cliente":  fake.ipv4(),
        "endpoint":    endpoint,
        "metodo":      random.choice(METODOS),
        "codigo_http": codigo,
        "latencia_ms": latencia,
    }


# ─── Insercion ────────────────────────────────────────────────────────────────

def preparar_statements(session) -> tuple:
    """Prepara los dos statements de insercion (doble-write)."""

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


def params_hora(log: dict) -> tuple:
    return (
        log["fecha"],
        log["hora"],
        log["log_id"],
        log["ip_cliente"],
        log["endpoint"],
        log["metodo"],
        log["codigo_http"],
        log["latencia_ms"],
        log["ts"],
    )


def params_endpoint(log: dict) -> tuple:
    return (
        log["endpoint"],
        log["ts"],
        log["log_id"],
        log["ip_cliente"],
        log["metodo"],
        log["codigo_http"],
        log["latencia_ms"],
    )


def insertar_lote(session, stmt_hora, stmt_endpoint, lote: list) -> None:
    """Inserta un lote usando execute_concurrent_with_args para mayor velocidad."""
    params_h = [params_hora(log)     for log in lote]
    params_e = [params_endpoint(log) for log in lote]

    execute_concurrent_with_args(session, stmt_hora,     params_h, concurrency=CONCURRENCIA)
    execute_concurrent_with_args(session, stmt_endpoint, params_e, concurrency=CONCURRENCIA)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    fake = Faker()
    Faker.seed(42)
    random.seed(42)

    cluster, session = conectar()
    stmt_hora, stmt_endpoint = preparar_statements(session)

    print("Iniciando generacion de {:,} registros en lotes de {}...".format(
        TOTAL_REGISTROS, BATCH_SIZE
    ))
    print()

    lote           = []
    insertados     = 0
    errores        = 0
    inicio         = time.time()

    for i in range(1, TOTAL_REGISTROS + 1):
        lote.append(generar_log(fake))

        if len(lote) == BATCH_SIZE:
            try:
                insertar_lote(session, stmt_hora, stmt_endpoint, lote)
                insertados += len(lote)
            except Exception as exc:
                errores += len(lote)
                print("\n  [WARN] Lote fallido: {}".format(exc))
            finally:
                lote = []

            # Progreso cada 10 000 registros
            if insertados % 10_000 == 0:
                elapsed   = time.time() - inicio
                velocidad = insertados / elapsed if elapsed > 0 else 0
                pct       = (insertados / TOTAL_REGISTROS) * 100
                print("  {:>7,.0f} / {:,}  ({:.1f}%)  {:.0f} reg/s".format(
                    insertados, TOTAL_REGISTROS, pct, velocidad
                ))

    # Insertar el residuo del ultimo lote incompleto
    if lote:
        try:
            insertar_lote(session, stmt_hora, stmt_endpoint, lote)
            insertados += len(lote)
        except Exception as exc:
            errores += len(lote)
            print("\n  [WARN] Ultimo lote fallido: {}".format(exc))

    elapsed = time.time() - inicio
    print()
    print("=" * 50)
    print("Generacion completada")
    print("  Insertados : {:,}".format(insertados))
    print("  Errores    : {:,}".format(errores))
    print("  Tiempo     : {:.1f}s".format(elapsed))
    print("  Velocidad  : {:.0f} reg/s".format(insertados / elapsed if elapsed > 0 else 0))
    print("=" * 50)
    print()
    print("Ahora puedes abrir el dashboard: python app.py")

    cluster.shutdown()


if __name__ == "__main__":
    main()
