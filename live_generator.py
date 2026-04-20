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

CASSANDRA_HOST     = "127.0.0.1"
CASSANDRA_PORT     = 9042
KEYSPACE           = "log_simulator"

REGISTROS_POR_LOTE = 15    # logs normales por rafaga
PAUSA_SEGUNDOS     = 2     # segundos entre rafagas

# Cada cuantos lotes se evalua si bloquear una IP automaticamente
LOTES_ENTRE_BLOQUEOS  = 15   # ~30 segundos
# Cada cuantos lotes se desbloquea una IP automaticamente
LOTES_ENTRE_DESBLOQUEOS = 25  # ~50 segundos

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

MOTIVOS_AUTO = [
    "Demasiados errores 500",
    "Fuerza bruta detectada",
    "Actividad sospechosa",
    "Acceso no autorizado",
]

NIVELES_AUTO = ["BAJO", "MEDIO", "ALTO"]


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


# ─── Statements ───────────────────────────────────────────────────────────────

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


# ─── Insercion de log normal ──────────────────────────────────────────────────

def insertar_log(session, stmt_hora, stmt_endpoint, ip=None, fake=None):
    ahora    = datetime.utcnow()
    log_id   = uuid.uuid4()
    endpoint = random.choices(ENDPOINT_NAMES, weights=ENDPOINT_PESOS, k=1)[0]
    metodo   = random.choice(METODOS)
    codigo   = random.choice(CODIGOS)
    ip       = ip or (fake.ipv4() if fake else "10.0.0.1")

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


# ─── Logica de bloqueo automatico ────────────────────────────────────────────

def obtener_ips_bloqueadas(session):
    """Retorna lista de IPs actualmente bloqueadas."""
    rows = session.execute("SELECT ip FROM ips_bloqueadas")
    return [row.ip for row in rows]


def bloquear_ip_automatica(session, fake):
    """Bloquea una IP aleatoria nueva y simula intentos de acceso."""
    ip     = fake.ipv4()
    motivo = random.choice(MOTIVOS_AUTO)
    nivel  = random.choices(NIVELES_AUTO, weights=[40, 35, 25], k=1)[0]
    ahora  = datetime.utcnow()

    # INSERT en ips_bloqueadas
    session.execute(
        """INSERT INTO ips_bloqueadas
           (ip, motivo, nivel, bloqueada_en, intentos)
           VALUES (%s, %s, %s, %s, %s)""",
        (ip, motivo, nivel, ahora, 0)
    )

    # Simular 2-4 intentos de acceso desde esa IP
    n_intentos = random.randint(2, 4)
    for _ in range(n_intentos):
        ep  = random.choice(ENDPOINT_NAMES)
        met = random.choice(["GET", "POST"])
        session.execute(
            """INSERT INTO intentos_bloqueados
               (ip, ts, endpoint, metodo)
               VALUES (%s, %s, %s, %s)""",
            (ip, datetime.utcnow(), ep, met)
        )
        session.execute(
            "UPDATE ips_bloqueadas SET intentos = intentos + 1 WHERE ip=%s", (ip,)
        )
        time.sleep(0.1)

    print("  [FIREWALL] IP bloqueada automaticamente: {} | {} | {} | {} intentos".format(
        ip, nivel, motivo, n_intentos
    ))
    return ip


def desbloquear_ip_automatica(session, ips_actuales):
    """Desbloquea una IP aleatoria de las que estan bloqueadas (simula resolucion)."""
    if not ips_actuales:
        return
    ip = random.choice(ips_actuales)
    session.execute("DELETE FROM ips_bloqueadas WHERE ip=%s", (ip,))
    print("  [FIREWALL] IP desbloqueada automaticamente: {} (amenaza resuelta)".format(ip))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    fake    = Faker()
    cluster, session = conectar()
    stmt_hora, stmt_endpoint = preparar_statements(session)

    total   = 0
    errores = 0
    lotes   = 0
    inicio  = time.time()

    print()
    print("Generando {} logs cada {}s con bloqueos automaticos simulados.".format(
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
            lotes += 1

            # ── Logs normales ──
            for _ in range(REGISTROS_POR_LOTE):
                try:
                    endpoint, metodo, codigo, latencia = insertar_log(
                        session, stmt_hora, stmt_endpoint, fake=fake
                    )
                    total += 1
                    if codigo >= 500:
                        errores += 1

                    if total % 3 == 0:
                        ts    = datetime.utcnow().strftime("%H:%M:%S")
                        marca = " <- ERROR" if codigo >= 500 else ""
                        print("{:<8} {:<6} {:<22} {:<7} {:<6}{}".format(
                            ts, metodo, endpoint, codigo, latencia, marca
                        ))
                except Exception as exc:
                    print("  [WARN] Error al insertar log:", exc)

            # ── Resumen de lote ──
            elapsed = time.time() - inicio
            print("  -> Lote {} | Total: {:,} | Errores: {:,} | {:.0f}s".format(
                lotes, total, errores, elapsed
            ))
            print()

            # ── Bloqueo automatico cada N lotes ──
            if lotes % LOTES_ENTRE_BLOQUEOS == 0:
                try:
                    bloquear_ip_automatica(session, fake)
                except Exception as exc:
                    print("  [WARN] Error al bloquear IP:", exc)

            # ── Desbloqueo automatico cada N lotes ──
            if lotes % LOTES_ENTRE_DESBLOQUEOS == 0:
                try:
                    ips = obtener_ips_bloqueadas(session)
                    # Solo desbloquear IPs de nivel BAJO para que las de ALTO persistan
                    rows = session.execute(
                        "SELECT ip FROM ips_bloqueadas WHERE nivel='BAJO' ALLOW FILTERING"
                    )
                    bajas = [r.ip for r in rows]
                    if bajas:
                        desbloquear_ip_automatica(session, bajas)
                except Exception as exc:
                    print("  [WARN] Error al desbloquear IP:", exc)

            time.sleep(PAUSA_SEGUNDOS)

    except KeyboardInterrupt:
        elapsed = time.time() - inicio
        print()
        print("=" * 50)
        print("Generador detenido.")
        print("  Insertados : {:,}".format(total))
        print("  Errores    : {:,}".format(errores))
        print("  Lotes      : {:,}".format(lotes))
        print("  Tiempo     : {:.1f}s".format(elapsed))
        print("=" * 50)
        cluster.shutdown()


if __name__ == "__main__":
    main()