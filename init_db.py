"""Inicializa la base de datos: recrea tablas y carga datos de prueba.

Uso:
    python init_db.py

Genera agenda.db con 5 médicos, bloques DISPONIBLES para los próximos 5 días
y los usuarios por defecto para el login.
"""

import sqlite3
from datetime import date, timedelta

from auth import hash_password
from database import DB_PATH, SCHEMA, get_connection

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


def seed_usuarios(conn: sqlite3.Connection) -> int:
    cursor = conn.cursor()
    for usuario, nombre, password, rol, medico_id in USUARIOS:
        cursor.execute(
            "INSERT INTO usuarios (usuario, nombre, password_hash, rol, medico_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (usuario, nombre, hash_password(password), rol, medico_id),
        )
    return len(USUARIOS)


def main() -> None:
    conn = get_connection()
    try:
        conn.executescript(
            "DROP TABLE IF EXISTS sesiones;"
            " DROP TABLE IF EXISTS citas;"
            " DROP TABLE IF EXISTS bloques_horarios;"
            " DROP TABLE IF EXISTS usuarios;"
            " DROP TABLE IF EXISTS medicos;"
        )
        conn.executescript(SCHEMA)

        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO medicos (nombre, especialidad) VALUES (?, ?)", MEDICOS
        )
        medicos_insertados = cursor.rowcount

        bloques_insertados = seed_bloques(conn)
        usuarios_insertados = seed_usuarios(conn)
        conn.commit()
    finally:
        conn.close()

    print(f"Base de datos creada en: {DB_PATH}")
    print(f"Médicos insertados:     {medicos_insertados}")
    print(f"Bloques disponibles:    {bloques_insertados} "
          f"({DIAS} días x {HORA_FIN - HORA_INICIO} horas x {medicos_insertados} médicos)")
    print("Usuarios por defecto:   ")
    for usuario, nombre, password, rol, _ in USUARIOS:
        print(f"  - {usuario:<11} / {password:<13} ({rol}) - {nombre}")


if __name__ == "__main__":
    main()
