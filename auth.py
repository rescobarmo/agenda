"""Autenticación: hash de contraseñas y manejo de sesiones (tokens)."""

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

ITERACIONES = 120_000
DURACION_SESION_HORAS = 12


def hash_password(password: str) -> str:
    """Devuelve 'salt_hex$hash_hex' usando PBKDF2-SHA256."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERACIONES)
    return salt.hex() + "$" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERACIONES)
        return secrets.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def crear_sesion(conn: sqlite3.Connection, usuario_id: int) -> str:
    token = secrets.token_hex(32)
    ahora = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO sesiones (token, usuario_id, fecha_creacion, expira_en)"
        " VALUES (?, ?, ?, ?)",
        (
            token,
            usuario_id,
            ahora.isoformat(),
            (ahora + timedelta(hours=DURACION_SESION_HORAS)).isoformat(),
        ),
    )
    return token


def validar_sesion(conn: sqlite3.Connection, token: str):
    """Devuelve el usuario de la sesión o None si es inválida/expirada."""
    if not token:
        return None
    fila = conn.execute(
        "SELECT s.token, s.usuario_id, s.expira_en,"
        "       u.usuario, u.nombre, u.rol, u.medico_id"
        " FROM sesiones s"
        " JOIN usuarios u ON u.id = s.usuario_id"
        " WHERE s.token = ?",
        (token,),
    ).fetchone()
    if not fila:
        return None
    if fila["expira_en"] < datetime.now(timezone.utc).isoformat():
        conn.execute("DELETE FROM sesiones WHERE token = ?", (token,))
        conn.commit()
        return None
    return dict(fila)


def eliminar_sesion(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sesiones WHERE token = ?", (token,))
    conn.commit()
