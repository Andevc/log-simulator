# Log Simulator — Guía de instalación y ejecución

**Universidad Mayor de San Andrés · Bases de Datos 3**  
**Tecnologías:** Apache Cassandra 4.1 · Flask · Python · Docker · Chart.js

---

## Requisitos previos

Antes de empezar, instala estas dos herramientas:

| Herramienta | Dónde descargar |
|---|---|
| Docker Desktop | https://www.docker.com/products/docker-desktop |
| Python 3.8 o superior | https://www.python.org/downloads |

> **Importante en Windows:** Al instalar Python, marca la casilla **"Add Python to PATH"** antes de hacer click en Install Now. Si no lo haces, ningún comando `python` va a funcionar en la terminal.

---

## Estructura del proyecto

```
log-simulator/
├── docker-compose.yml     ← levanta Cassandra en Docker
├── requirements.txt       ← dependencias Python
├── setup_db.py            ← crea el keyspace y las tablas
├── generator.py           ← genera 50k-500k logs masivos
├── seed_ips.py            ← precarga IPs bloqueadas para la expo
├── live_generator.py      ← genera logs en tiempo real + bloqueos automáticos
├── app.py                 ← backend Flask con todos los endpoints REST
└── static/
    ├── index.html         ← dashboard principal
    ├── dashboard.js       ← lógica del dashboard, refresco cada 3s
    └── usuario.html       ← simulador de usuario interactivo
```

---

## Paso 1 — Abrir la terminal en la carpeta del proyecto

**Windows:** Abre la carpeta `log-simulator`, clic derecho en espacio vacío → "Abrir en Terminal"  
O abre CMD/PowerShell y escribe:
```
cd C:\ruta\a\log-simulator
```

---

## Paso 2 — Instalar dependencias Python

```
pip install -r requirements.txt
```

Si `pip` no se reconoce, usa:
```
python -m pip install -r requirements.txt
```

Esto instala: `cassandra-driver`, `Flask`, `Faker`, `Werkzeug`.

---

## Paso 3 — Levantar Cassandra con Docker

Primero abre **Docker Desktop** y espera a que esté corriendo (ícono en la barra de tareas).

Luego ejecuta:
```
docker compose up -d
```

Esto descarga la imagen de Cassandra (solo la primera vez, ~500MB) y la inicia en segundo plano.

**Espera 30-60 segundos** antes del siguiente paso. Cassandra tarda en arrancar.

Para verificar que está lista:
```
docker compose logs cassandra
```
Busca la línea: `Starting listening for CQL clients` — cuando aparezca, está lista.

---

## Paso 4 — Crear la base de datos

```
python setup_db.py
```

Este script:
- Espera automáticamente a que Cassandra esté disponible
- Crea el keyspace `log_simulator`
- Crea las 4 tablas: `logs_por_hora`, `logs_por_endpoint`, `ips_bloqueadas`, `intentos_bloqueados`

Resultado esperado:
```
Esperando a que Cassandra este disponible OK
Creando keyspace y tablas...
Schema creado correctamente.

Tablas disponibles en keyspace 'log_simulator':
  - logs_por_hora
  - logs_por_endpoint
  - ips_bloqueadas
  - intentos_bloqueados
```

> Solo necesitas ejecutar esto **una vez**. Si lo vuelves a ejecutar no hay problema, usa `IF NOT EXISTS`.

---

## Paso 5 — Generar datos masivos

```
python generator.py
```

Genera registros de logs de acceso web y los inserta en Cassandra usando el patrón doble-write (escribe en `logs_por_hora` y `logs_por_endpoint` simultáneamente).

Verás el progreso en pantalla:
```
Conectando a Cassandra... OK
Iniciando generacion de 50,000 registros en lotes de 200...

    10,000 / 50,000  (20.0%)  3,241 reg/s
    20,000 / 50,000  (40.0%)  3,189 reg/s
    ...

Generacion completada
  Insertados : 50,000
  Tiempo     : 15.4s
```

**Espera a que aparezca "Generacion completada"** antes de continuar.

> Para cambiar la cantidad de registros, abre `generator.py` y modifica la línea:
> `TOTAL_REGISTROS = 50_000`  ← cámbialo a 100_000 si quieres más datos

---

## Paso 6 — Precargar IPs bloqueadas (para la exposición)

```
python seed_ips.py
```

Inserta 6 IPs bloqueadas con distintos niveles de amenaza (BAJO/MEDIO/ALTO), motivos predefinidos e historial de intentos. Esto hace que el panel Firewall del dashboard no esté vacío al iniciar la expo.

Resultado esperado:
```
[ALTO]   185.220.101.45 — Fuerza bruta detectada — 47 intentos
[ALTO]   194.165.16.72  — Demasiados errores 500 — 23 intentos
[MEDIO]  45.155.205.233 — Acceso no autorizado — 12 intentos
[MEDIO]  91.108.4.18    — Actividad sospechosa — 8 intentos
[BAJO]   103.74.19.104  — IP desconocida — 3 intentos
[BAJO]   77.88.5.214    — Mantenimiento — 1 intentos
```

> Solo ejecutar **una vez**. Si lo ejecutas de nuevo duplica las IPs.

---

## Paso 7 — Arrancar el servidor (Terminal 1)

Abre una terminal y ejecuta:
```
python app.py
```

Deja esta terminal abierta. Resultado esperado:
```
Cassandra conectada OK

Dashboard disponible en: http://localhost:5000
Presiona Ctrl+C para detener.

 * Running on http://127.0.0.1:5000
 * Running on http://192.168.x.x:5000
```

---

## Paso 8 — Arrancar el generador en tiempo real (Terminal 2)

Abre **otra terminal** (sin cerrar la anterior) y ejecuta:
```
python live_generator.py
```

Este script genera 15 logs cada 2 segundos y cada ~30 segundos bloquea automáticamente una IP nueva. Deja esta terminal abierta también.

---

## Paso 9 — Abrir el dashboard en el navegador

Abre tu navegador y ve a:

| URL | Qué muestra |
|---|---|
| http://localhost:5000 | Dashboard principal con gráficas y panel Firewall |
| http://localhost:5000/usuario | Simulador de usuario interactivo |

---

## Resumen del orden de ejecución

```
Terminal única (pasos 2-6, uno por uno):
  pip install -r requirements.txt
  docker compose up -d
  python setup_db.py
  python generator.py
  python seed_ips.py

Terminal 1 (dejar corriendo):
  python app.py

Terminal 2 (dejar corriendo):
  python live_generator.py

Navegador:
  http://localhost:5000          ← dashboard
  http://localhost:5000/usuario  ← simulador
```

---

## Cómo demostrar el CRUD en la exposición

1. Abre el simulador (`/usuario`) — anota la IP que aparece arriba en verde
2. En el dashboard, panel **Firewall**, escribe esa IP, selecciona motivo y nivel, haz click en **Bloquear IP**
3. Vuelve al simulador e intenta cualquier acción → aparece overlay rojo "ACCESO DENEGADO"
4. El intento queda registrado en el **Historial de intentos bloqueados** del dashboard
5. Cambia el motivo o nivel desde los dropdowns inline y haz click en **Guardar** → eso es el UPDATE
6. Haz click en **Eliminar** → la IP se desbloquea, el simulador vuelve a funcionar

---

## Comandos útiles de Docker

```bash
# Ver si Cassandra está corriendo
docker compose ps

# Ver los logs de Cassandra
docker compose logs cassandra

# Detener Cassandra (conserva los datos)
docker compose stop

# Borrar todo incluyendo datos
docker compose down -v
```

## Conectarse a Cassandra directamente

```bash
docker exec -it cassandra_log cqlsh
```

Una vez dentro:
```sql
USE log_simulator;
DESCRIBE TABLES;
SELECT count(*) FROM logs_por_hora;
SELECT count(*) FROM logs_por_endpoint;
SELECT * FROM ips_bloqueadas;
```

---

## Solución de problemas

**"No se pudo conectar a Cassandra"**
→ Espera 30-60 segundos más y vuelve a ejecutar el script.
→ Verifica que Docker Desktop esté abierto y el contenedor corriendo con `docker compose ps`.

**"pip no se reconoce como comando"**
→ Reinstala Python marcando "Add Python to PATH".
→ O usa: `python -m pip install -r requirements.txt`

**"Port 9042 already in use"**
→ Ya tienes Cassandra corriendo. Ejecuta `docker compose down` y vuelve a intentar.

**El dashboard muestra "—" en los KPIs**
→ Asegúrate de haber ejecutado `generator.py` completamente.
→ Recarga la página con F5.

**"/usuario" muestra "Not Found"**
→ Reinicia `app.py` con Ctrl+C y vuelve a ejecutarlo. El archivo `usuario.html` debe estar dentro de la carpeta `static/`.

**"dashboard.js 404"**
→ En `static/index.html` busca la última línea con `<script>` y asegúrate que diga:
→ `<script src="/static/dashboard.js"></script>`