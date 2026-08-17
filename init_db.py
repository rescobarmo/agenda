"""Inicializa la base de datos: recrea tablas y carga datos de prueba.

Uso:
    python init_db.py

Genera agenda.db con 5 médicos, bloques DISPONIBLES para los próximos 5 días
y los usuarios por defecto para el login.
"""

from database import (
    DB_PATH,
    MEDICOS,
    USUARIOS,
    DIAS,
    HORA_FIN,
    HORA_INICIO,
    SCHEMA,
    get_connection,
    seed_bloques,
    seed_usuarios,
)


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