from __future__ import annotations

import sys
import time
import uuid
from datetime import datetime, timedelta

from cassandra.cluster import Cluster
from cassandra.policies import RoundRobinPolicy


CASSANDRA_HOST = "127.0.0.1"
CASSANDRA_PORT = 9042
KEYSPACE       = "log_simulator"

IPS_SEED = [
    ("185.220.101.45", "Fuerza bruta detectada",   "ALTO",  47, 120),
    ("194.165.16.72",  "Demasiados errores 500",   "ALTO",  23,  90),
    ("45.155.205.233", "Acceso no autorizado",     "MEDIO", 12,  60),
    ("91.108.4.18",    "Actividad sospechosa",     "MEDIO",  8,  45),
    ("103.74.19.104",  "IP desconocida",           "BAJO",   3,  30),
    ("77.88.5.214",    "Mantenimiento",            "BAJO",   1,  15),
]

INTENTOS_SEED = [
    ("/api/auth/login",  "POST"),
    ("/api/users",       "GET"),
    ("/api/payments",    "POST"),
    ("/api/auth/login",  "POST"),
    ("/api/orders",      "DELETE"),
]


def conectar():
    print("Conectando a Cassandra...", end=" ", flush=True)
    for _ in range(10):
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
        except Exception:
            print(".", end="", flush=True)
            time.sleep(3)
    print("\nERROR: No se pudo conectar.")
    sys.exit(1)


def seed(session):
    ahora = datetime.utcnow()
    print()
    print("Insertando IPs bloqueadas...")

    for ip, motivo, nivel, intentos, minutos_atras in IPS_SEED:
        ts_bloqueo = ahora - timedelta(minutes=minutos_atras)

        # INSERT ip bloqueada
        session.execute(
            """INSERT INTO ips_bloqueadas
               (ip, motivo, nivel, bloqueada_en, intentos)
               VALUES (%s, %s, %s, %s, %s)""",
            (ip, motivo, nivel, ts_bloqueo, intentos)
        )

        # INSERT intentos en el historial
        for i in range(min(intentos, 5)):
            ts_intento = ts_bloqueo + timedelta(minutes=i * 3 + 1)
            ep, met    = INTENTOS_SEED[i % len(INTENTOS_SEED)]
            session.execute(
                """INSERT INTO intentos_bloqueados
                   (ip, ts, endpoint, metodo)
                   VALUES (%s, %s, %s, %s)""",
                (ip, ts_intento, ep, met)
            )

        nivel_fmt = "[{}]".format(nivel).ljust(8)
        print("  {} {} — {} — {} intentos".format(nivel_fmt, ip, motivo, intentos))

    print()
    print("Seed completado. {} IPs bloqueadas cargadas.".format(len(IPS_SEED)))
    print("Abre el dashboard y ve al panel Firewall para verlas.")


def main():
    cluster, session = conectar()
    seed(session)
    cluster.shutdown()


if __name__ == "__main__":
    main()