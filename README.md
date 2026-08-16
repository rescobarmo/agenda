# Sistema de Citas - Backend (FastAPI + SQLite) y Web

Backend ligero para gestionar el agendamiento de citas de una clínica pequeña
(hasta 5 médicos). Usa **FastAPI** y **SQLite** en modo **WAL** con
`busy_timeout` para soportar concurrencia entre la web y WhatsApp.

Incluye una **interfaz web** (un solo archivo `index.html`) con Tailwind CSS y
JavaScript vanilla que se sirve directamente desde el backend.

## Estructura

```
agenda/
├── auth.py         # Hash de contraseñas (PBKDF2) y sesiones por token
├── database.py     # Conexión SQLite (WAL + busy_timeout) y esquema
├── init_db.py      # Crea agenda.db, datos de prueba y usuarios por defecto
├── main.py         # API FastAPI (login + endpoints protegidos) + sirve index.html
├── index.html      # Interfaz web (Tailwind CSS + JS vanilla)
├── requirements.txt
└── README.md
```

## 1) Instalación

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

## 2) Inicializar la base de datos

Crea `agenda.db` con las tablas `medicos`, `bloques_horarios`, `citas`,
`usuarios` y `sesiones`, genera bloques `DISPONIBLE` para los próximos 5 días
(09:00-17:00, bloques de 1 hora) para los 5 médicos, y crea los usuarios por
defecto para el login:

| Usuario   | Contraseña     | Rol            | Médico vinculado |
|-----------|----------------|----------------|------------------|
| admin     | admin123       | admin          | —                |
| recepcion | recepcion123   | recepcionista  | —                |
| medico1   | medico123      | medico         | Dr. Ana Torres   |
| medico2   | medico123      | medico         | Dr. Luis Pérez   |
| medico3   | medico123      | medico         | Dra. María García|
| medico4   | medico123      | medico         | Dr. Carlos Ruiz  |
| medico5   | medico123      | medico         | Dra. Lucía Fernández |

```bash
python init_db.py
```

> El archivo `main.py` crea las tablas automáticamente al arrancar si no existen,
> por lo que el paso 2 es opcional (solo se necesita para recargar los datos de prueba).

## 3) Ejecutar el servidor

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

- **Interfaz web**: http://127.0.0.1:8000/ (se sirve `index.html`)
- Documentación interactiva (Swagger): http://127.0.0.1:8000/docs
- Documentación en JSON: http://127.0.0.1:8000/openapi.json

> El backend incluye CORS abierto, por lo que `index.html` también funciona
> abriéndolo directamente en el navegador (buscará la API en `http://127.0.0.1:8000`).

## 4) Acceso (login)

Al abrir la web aparece una **pantalla de login**. Ingresa cualquiera de los
usuarios de la tabla anterior. Todos los endpoints de la API (salvo
`/api/auth/login`) exigen el token en el encabezado:

```http
Authorization: Bearer <token>
```

- El token dura 12 horas y se guarda en `localStorage` del navegador.
- Si una sesión expira, la web regresa automáticamente al login.
- Los usuarios con rol `medico` ven solo la agenda de su médico (el selector
  de médico aparece fijado y deshabilitado).

## 5) Interfaz web (index.html)

Se sirve en la raíz del servidor y funciona en móviles y escritorio. Incluye:

- **Agendar cita**: selector de médico, franja de fechas (próximos 14 días),
  rejilla de horarios disponibles, y un modal con los datos del paciente que
  muestra el resumen y el **código de cancelación** al confirmar.
- **Mis citas**: busca la cita por **código de cancelación** o por **teléfono**,
  la muestra y permite cancelarla (con confirmación en dos pasos).
- **Calendario**: vista semanal tipo Google Calendar con las **horas agendadas
  por médico** (chips por paciente y hora), navegación entre semanas, botón
  "Hoy" y detalle al hacer clic en una cita. Incluye un **selector de médico**
  para filtrar la agenda de un solo doctor (o ver a todos), y un botón
  **"Pantalla completa"** que abre el calendario ocupando todo el viewport.
  Se puede abrir directamente con `http://127.0.0.1:8000/#calendario`
  (también `#citas` para "Mis citas", `#calendario-full` para la vista a
  pantalla completa, y `?med={id}` para abrir ya filtrado por médico, p. ej.
  `#calendario?med=2`).

Carga todos los datos con `fetch()` a la API, con spinners de carga,
notificaciones (toasts) de éxito/error y validaciones en cada formulario.

## 6) Endpoints de la API

Todos los endpoints requieren `Authorization: Bearer <token>` salvo
`POST /api/auth/login`.

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/auth/login` | Inicia sesión (`usuario`, `password`) y devuelve `token` |
| GET  | `/api/auth/me` | Usuario de la sesión actual |
| POST | `/api/auth/logout` | Cierra la sesión (invalida el token) |
| GET  | `/api/medicos` | Lista los médicos |
| GET  | `/api/disponibilidad?medico_id={id}&fecha={YYYY-MM-DD}` | Bloques `DISPONIBLE` |
| GET  | `/api/citas?id_cancelacion={código}` o `?telefono={tel}` | Consulta citas (usado por "Mis citas") |
| GET  | `/api/citas?medico_id={id}&fecha_inicio={D}&fecha_fin={D}` | Citas por rango de fechas (usado por el calendario) |
| POST | `/api/agendar` | Agenda una cita y devuelve `id_cancelacion` |
| POST | `/api/cancelar` | Cancela por `id_cancelacion` o por `cita_id` + `telefono` |
| POST | `/api/bloquear-hora` | Marca un bloque como `OCUPADO` manualmente |

## 7) Pruebas de los endpoints con curl

### POST /api/auth/login (obtener token)
```bash
curl -X POST http://127.0.0.1:8000/api/auth/login ^
  -H "Content-Type: application/json" ^
  -d "{\"usuario\":\"admin\",\"password\":\"admin123\"}"
```

> La respuesta incluye `token`. Úsalo en las demás peticiones con el encabezado
> `-H "Authorization: Bearer <TOKEN>"`.

### GET /api/medicos
```bash
curl http://127.0.0.1:8000/api/medicos ^
  -H "Authorization: Bearer <TOKEN>"
```

### GET /api/disponibilidad (usa una fecha real; ajusta YYYY-MM-DD)
```bash
curl "http://127.0.0.1:8000/api/disponibilidad?medico_id=1&fecha=2026-08-11" ^
  -H "Authorization: Bearer <TOKEN>"
```

### POST /api/agendar
```bash
curl -X POST http://127.0.0.1:8000/api/agendar ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer <TOKEN>" ^
  -d "{\"bloque_id\":1,\"paciente_nombre\":\"Juan Perez\",\"paciente_telefono\":\"3123456789\",\"paciente_email\":\"juan@mail.com\"}"
```

> La respuesta incluye `id_cancelacion`, el código único para cancelar.
> En Linux/macOS usa `\` en lugar de `^` para continuar líneas.

### POST /api/cancelar (por código de cancelación)
```bash
curl -X POST http://127.0.0.1:8000/api/cancelar ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer <TOKEN>" ^
  -d "{\"id_cancelacion\":\"<CODIGO_OBTENIDO_AL_AGENDAR>\"}"
```

### POST /api/cancelar (por cita_id + teléfono)
```bash
curl -X POST http://127.0.0.1:8000/api/cancelar ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer <TOKEN>" ^
  -d "{\"cita_id\":1,\"telefono\":\"3123456789\"}"
```

### POST /api/bloquear-hora (administración)
```bash
curl -X POST http://127.0.0.1:8000/api/bloquear-hora ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer <TOKEN>" ^
  -d "{\"medico_id\":1,\"fecha\":\"2026-08-12\",\"hora_inicio\":\"09:00\",\"hora_fin\":\"10:00\"}"
```

## Reglas de negocio implementadas

- `GET /api/disponibilidad` devuelve **solo** bloques con estado `DISPONIBLE`.
- `POST /api/agendar` valida que el bloque siga `DISPONIBLE`, lo pasa a `OCUPADO`
  y registra la cita dentro de una transacción `BEGIN IMMEDIATE` (evita doble
  reserva en concurrencia). Devuelve `id_cancelacion`.
- `POST /api/cancelar` elimina la cita y **libera el bloque a `DISPONIBLE` al instante**
  de forma atómica.
- `POST /api/bloquear-hora` permite marcar manualmente un bloque como `OCUPADO`.

## Concurrencia (SQLite en WAL)

Cada conexión ejecuta:

```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
```

Esto permite que varios procesos (la web y WhatsApp) escriban sin bloquearse,
y hace que las escrituras esperen hasta 5 segundos antes de fallar.
