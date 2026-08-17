"""Configuración y utilidades de la base de datos SQLite (modo WAL)."""

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from auth import hash_password

DB_PATH = Path(__file__).resolve().parent / "agenda.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS medicos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre       TEXT NOT NULL,
    especialidad TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bloques_horarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    medico_id   INTEGER NOT NULL REFERENCES medicos(id),
    fecha       TEXT NOT NULL,
    hora_inicio TEXT NOT NULL,
    hora_fin    TEXT NOT NULL,
    estado      TEXT NOT NULL DEFAULT 'DISPONIBLE'
                CHECK (estado IN ('DISPONIBLE', 'OCUPADO'))
);

CREATE TABLE IF NOT EXISTS citas (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    bloque_id         INTEGER NOT NULL UNIQUE REFERENCES bloques_horarios(id),
    paciente_nombre   TEXT NOT NULL,
    paciente_rut      TEXT NOT NULL DEFAULT '',
    paciente_telefono TEXT NOT NULL,
    paciente_email    TEXT,
    id_cancelacion    TEXT NOT NULL UNIQUE,
    fecha_creacion    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario       TEXT NOT NULL UNIQUE,
    nombre        TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    rol           TEXT NOT NULL DEFAULT 'recepcionista'
                  CHECK (rol IN ('admin', 'recepcionista', 'medico')),
    medico_id     INTEGER REFERENCES medicos(id)
);

CREATE TABLE IF NOT EXISTS sesiones (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    token          TEXT NOT NULL UNIQUE,
    usuario_id     INTEGER NOT NULL REFERENCES usuarios(id),
    fecha_creacion TEXT NOT NULL,
    expira_en      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recetas (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    cita_id           INTEGER REFERENCES citas(id),
    paciente_nombre   TEXT NOT NULL,
    paciente_rut      TEXT NOT NULL DEFAULT '',
    paciente_telefono TEXT NOT NULL,
    medico_id         INTEGER REFERENCES medicos(id),
    medicamentos      TEXT NOT NULL,
    indicaciones      TEXT NOT NULL DEFAULT '',
    fecha_creacion    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS examenes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    cita_id           INTEGER REFERENCES citas(id),
    paciente_nombre   TEXT NOT NULL,
    paciente_rut      TEXT NOT NULL DEFAULT '',
    paciente_telefono TEXT NOT NULL,
    medico_id         INTEGER REFERENCES medicos(id),
    nombre_archivo    TEXT NOT NULL,
    ruta_archivo      TEXT NOT NULL,
    tipo_mime         TEXT NOT NULL,
    tamano_bytes      INTEGER NOT NULL,
    fecha_creacion    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bloques_medico_fecha
    ON bloques_horarios (medico_id, fecha);

CREATE INDEX IF NOT EXISTS idx_sesiones_token
    ON sesiones (token);
"""


SCHEMA_INDICES = """
CREATE INDEX IF NOT EXISTS idx_recetas_telefono
    ON recetas (paciente_telefono);

CREATE INDEX IF NOT EXISTS idx_examenes_telefono
    ON examenes (paciente_telefono);

CREATE INDEX IF NOT EXISTS idx_citas_rut
    ON citas (paciente_rut);

CREATE INDEX IF NOT EXISTS idx_recetas_rut
    ON recetas (paciente_rut);

CREATE INDEX IF NOT EXISTS idx_examenes_rut
    ON examenes (paciente_rut);
"""


def get_connection() -> sqlite3.Connection:
    """Abre una conexión SQLite con WAL y timeout para concurrencia (web + WhatsApp)."""
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _migrate_rut(conn: sqlite3.Connection) -> None:
    """Agrega la columna paciente_rut a tablas existentes (no destructivo)."""
    for tabla in ("citas", "recetas", "examenes"):
        cols = {
            fila["name"]
            for fila in conn.execute(f"PRAGMA table_info({tabla})").fetchall()
        }
        if "paciente_rut" not in cols:
            conn.execute(
                f"ALTER TABLE {tabla}"
                " ADD COLUMN paciente_rut TEXT NOT NULL DEFAULT ''"
            )


def create_tables() -> None:
    """Crea las tablas si no existen (no destructivo)."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _migrate_rut(conn)
        conn.executescript(SCHEMA_INDICES)
        seed_if_empty(conn)


MEDICOS = [
    ("Dr. Ana Torres", "Medicina General"),
    ("Dr. Luis Pérez", "Pediatría"),
    ("Dra. María García", "Ginecología"),
    ("Dr. Carlos Ruiz", "Cardiología"),
    ("Dra. Lucía Fernández", "Dermatología"),
]

USUARIOS = [
    ("admin", "Administrador", "admin123", "admin", None),
    ("recepcion", "Recepcionista", "recepcion123", "recepcionista", None),
    ("medico1", "Dr. Ana Torres", "medico123", "medico", 1),
    ("medico2", "Dr. Luis Pérez", "medico123", "medico", 2),
    ("medico3", "Dra. María García", "medico123", "medico", 3),
    ("medico4", "Dr. Carlos Ruiz", "medico123", "medico", 4),
    ("medico5", "Dra. Lucía Fernández", "medico123", "medico", 5),
]

HORA_INICIO = 9       # primer bloque a las 09:00
HORA_FIN = 17         # último bloque empieza a las 16:00
DIAS = 5              # días (a partir de hoy) con agenda generada


def seed_usuarios(conn: sqlite3.Connection) -> int:
    cursor = conn.cursor()
    for usuario, nombre, password, rol, medico_id in USUARIOS:
        cursor.execute(
            "INSERT INTO usuarios (usuario, nombre, password_hash, rol, medico_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (usuario, nombre, hash_password(password), rol, medico_id),
        )
    return len(USUARIOS)


def seed_bloques(conn: sqlite3.Connection) -> int:
    """Genera un bloque de 1 hora por médico por día en el rango horario."""
    cursor = conn.cursor()
    hoy = date.today()
    total = 0
    for medico_id in range(1, len(MEDICOS) + 1):
        for delta in range(DIAS):
            fecha = (hoy + timedelta(days=delta)).isoformat()
            for h in range(HORA_INICIO, HORA_FIN):
                cursor.execute(
                    "INSERT INTO bloques_horarios"
                    " (medico_id, fecha, hora_inicio, hora_fin, estado)"
                    " VALUES (?, ?, ?, ?, 'DISPONIBLE')",
                    (medico_id, fecha, f"{h:02d}:00", f"{h + 1:02d}:00"),
                )
                total += 1
    return total


def seed_if_empty(conn: sqlite3.Connection) -> None:
    """Siembra datos por defecto solo si las tablas estan vacias (no destructivo)."""
    if conn.execute("SELECT COUNT(*) AS n FROM medicos").fetchone()["n"] == 0:
        conn.executemany(
            "INSERT INTO medicos (nombre, especialidad) VALUES (?, ?)", MEDICOS
        )
    if conn.execute("SELECT COUNT(*) AS n FROM usuarios").fetchone()["n"] == 0:
        seed_usuarios(conn)
    if conn.execute("SELECT COUNT(*) AS n FROM bloques_horarios").fetchone()["n"] == 0:
        seed_bloques(conn)
    conn.commit()
