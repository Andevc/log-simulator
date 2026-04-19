"""
setup_db.py - Inicializa el keyspace y las tablas en Cassandra local.
Ejecutar UNA SOLA VEZ antes de arrancar el generador o la app.

Uso:
    python setup_db.py
"""

from __future__ import annotations

import sys
import time

from cassandra.cluster import Cluster
from cassandra.policies import RoundRobinPolicy


CASSANDRA_HOST = "127.0.0.1"
CASSANDRA_PORT = 9042
MAX_RETRIES    = 20
RETRY_DELAY    = 5  # segundos entre reintentos


def wait_for_cassandra() -> "Session":
    """Reintenta la conexion hasta que Cassandra este lista."""
    print("Esperando a que Cassandra este disponible", end="", flush=True)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            cluster = Cluster(
                [CASSANDRA_HOST],
                port=CASSANDRA_PORT,
                load_balancing_policy=RoundRobinPolicy(),
                protocol_version=4,
            )
            session = cluster.connect()
            print(" OK")
            return session
        except Exception:
            print(".", end="", flush=True)
            time.sleep(RETRY_DELAY)

    print("\nERROR: No se pudo conectar a Cassandra despues de {} intentos.".format(MAX_RETRIES))
    print("Asegurate de que Docker este corriendo: docker compose up -d")
    sys.exit(1)


def create_schema(session) -> None:
    """Crea keyspace y tablas leyendo init.cql."""
    print("Creando keyspace y tablas...")

    ddl_statements = [
        """
        CREATE KEYSPACE IF NOT EXISTS log_simulator
            WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
            AND durable_writes = true
        """,
        "USE log_simulator",
        """
        CREATE TABLE IF NOT EXISTS logs_por_hora (
            fecha       DATE,
            hora        INT,
            log_id      UUID,
            ip_cliente  TEXT,
            endpoint    TEXT,
            metodo      TEXT,
            codigo_http INT,
            latencia_ms INT,
            ts          TIMESTAMP,
            PRIMARY KEY ((fecha, hora), log_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS logs_por_endpoint (
            endpoint    TEXT,
            ts          TIMESTAMP,
            log_id      UUID,
            ip_cliente  TEXT,
            metodo      TEXT,
            codigo_http INT,
            latencia_ms INT,
            PRIMARY KEY ((endpoint), ts, log_id)
        ) WITH CLUSTERING ORDER BY (ts DESC, log_id ASC)
        """,
        """
        CREATE TABLE IF NOT EXISTS ips_bloqueadas (
            ip           TEXT PRIMARY KEY,
            motivo       TEXT,
            nivel        TEXT,
            bloqueada_en TIMESTAMP,
            intentos     INT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS intentos_bloqueados (
            ip        TEXT,
            ts        TIMESTAMP,
            endpoint  TEXT,
            metodo    TEXT,
            PRIMARY KEY ((ip), ts)
        ) WITH CLUSTERING ORDER BY (ts DESC)
        """,
    ]

    for stmt in ddl_statements:
        session.execute(stmt.strip())

    print("Schema creado correctamente.")
    print()
    print("Tablas disponibles en keyspace 'log_simulator':")
    rows = session.execute("SELECT table_name FROM system_schema.tables WHERE keyspace_name='log_simulator'")
    for row in rows:
        print("  -", row.table_name)


def main() -> None:
    session = wait_for_cassandra()
    create_schema(session)
    print()
    print("Listo. Ahora puedes ejecutar:")
    print("  python generator.py       <- genera registros masivos")
    print("  python app.py             <- levanta el dashboard en http://localhost:5000")
    print("  python live_generator.py  <- genera logs en tiempo real (para la expo)")


if __name__ == "__main__":
    main()
