# Log Simulator — Apache Cassandra + Flask

Sistema de simulación y análisis de logs de acceso web a gran escala.  
Desarrollado para la materia **Bases de Datos 3** — Universidad Mayor de San Andrés.

---

## ¿Qué necesitas tener instalado?

| Herramienta | Versión mínima | Descarga |
|---|---|---|
| Docker Desktop | Cualquiera reciente | https://www.docker.com/products/docker-desktop/ |
| Python | 3.8 o superior | https://www.python.org/downloads/ |

> **Windows**: Al instalar Python, marca la casilla **"Add Python to PATH"**.

---

## Pasos para ejecutar el proyecto (en orden)

### 1. Descomprimir el ZIP

Extrae la carpeta `log-simulator` en cualquier lugar de tu PC.

### 2. Abrir una terminal en esa carpeta

En Windows: clic derecho dentro de la carpeta → **"Abrir en Terminal"**  
O abre CMD/PowerShell y navega con:
```
cd ruta\a\log-simulator
```

### 3. Instalar las dependencias de Python

```
pip install -r requirements.txt
```

### 4. Levantar Cassandra con Docker

```
docker compose up -d
```

Esto descarga la imagen de Cassandra (solo la primera vez) y la inicia en segundo plano.  
Espera unos **30-60 segundos** a que arranque completamente.

### 5. Crear la base de datos

```
python setup_db.py
```

Verás un mensaje de confirmación con las tablas creadas.  
Solo necesitas hacer esto **una vez**.

### 6. Generar los datos (500 000 registros)

```
python generator.py
```

Esto tarda entre **2 y 5 minutos** dependiendo del equipo.  
Verás el progreso en pantalla (velocidad en registros/segundo).

### 7. Arrancar el dashboard

```
python app.py
```

Luego abre tu navegador en: **http://localhost:5000**

---

## Arquitectura del proyecto

```
log-simulator/
├── docker-compose.yml   ← levanta Cassandra en Docker
├── requirements.txt     ← dependencias Python
├── setup_db.py          ← crea keyspace y tablas
├── generator.py         ← genera 500k logs con doble-write
├── app.py               ← backend Flask (6 endpoints REST)
└── static/
    ├── index.html       ← dashboard HTML
    └── dashboard.js     ← graficas Chart.js, refresco cada 3s
```

## Patrón doble-write explicado

El generador inserta cada log en **dos tablas** simultáneamente:

- `logs_por_hora` → partition key `(fecha, hora)` — optimizada para consultar rangos de tiempo
- `logs_por_endpoint` → partition key `(endpoint)` — optimizada para consultar por ruta

Esto es el núcleo del diseño NoSQL orientado a columnas: **una tabla por patrón de consulta**.

---

## Comandos útiles de Docker

```bash
# Ver si Cassandra está corriendo
docker compose ps

# Ver los logs de Cassandra (útil si algo falla)
docker compose logs cassandra

# Detener Cassandra
docker compose stop

# Borrar todo (borra también los datos)
docker compose down -v
```

## Conectarse a Cassandra directamente (opcional)

```bash
docker exec -it cassandra_log cqlsh
```

Una vez dentro:
```sql
USE log_simulator;
SELECT count(*) FROM logs_por_hora;
SELECT count(*) FROM logs_por_endpoint;
DESCRIBE TABLE logs_por_hora;
```

---

## Solución de problemas comunes

**"No se pudo conectar a Cassandra"**  
→ Espera un poco más y vuelve a ejecutar el script. Cassandra tarda en arrancar.  
→ Verifica que Docker Desktop esté abierto y corriendo.

**"pip no se reconoce como comando"**  
→ Asegúrate de instalar Python con "Add to PATH" marcado.  
→ Intenta con `python -m pip install -r requirements.txt`

**"Port 9042 already in use"**  
→ Ya tienes una instancia de Cassandra corriendo.  
→ Ejecuta `docker compose down` y vuelve a intentar.

**El dashboard muestra "—" en todos los KPIs**  
→ Asegúrate de haber ejecutado `generator.py` completamente antes de abrir la app.
