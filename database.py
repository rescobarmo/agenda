"""Configuración y utilidades de la base de datos SQLite (modo WAL)."""

import sqlite3
from pathlib import Path

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

CREATE INDEX IF NOT EXISTS idx_bloques_medico_fecha
    ON bloques_horarios (medico_id, fecha);

CREATE INDEX IF NOT EXISTS idx_sesiones_token
    ON sesiones (token);
"""


def get_connection() -> sqlite3.Connection:
    """Abre una conexión SQLite con WAL y timeout para concurrencia (web + WhatsApp)."""
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def create_tables() -> None:
    """Crea las tablas si no existen (no destructivo)."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
