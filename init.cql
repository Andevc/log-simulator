-- ============================================================
--  Log Simulator - Schema Cassandra
--  Ejecutar con: python setup_db.py
-- ============================================================

CREATE KEYSPACE IF NOT EXISTS log_simulator
    WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
    AND durable_writes = true;

USE log_simulator;

-- Tabla 1: Consultas por rango horario
-- Partition key compuesta (fecha + hora) -> agrupa todos los logs de una hora
-- Clustering key: log_id -> ordena dentro de la particion
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
);

-- Tabla 2: Consultas por endpoint (patron doble-write)
-- Partition key: endpoint -> todos los logs de /api/users en una particion
-- Clustering key: ts DESC + log_id -> los mas recientes primero
CREATE TABLE IF NOT EXISTS logs_por_endpoint (
    endpoint    TEXT,
    ts          TIMESTAMP,
    log_id      UUID,
    ip_cliente  TEXT,
    metodo      TEXT,
    codigo_http INT,
    latencia_ms INT,
    PRIMARY KEY ((endpoint), ts, log_id)
) WITH CLUSTERING ORDER BY (ts DESC, log_id ASC);
