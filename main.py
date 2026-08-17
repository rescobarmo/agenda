"""API REST para agendamiento de citas de una clínica pequeña.

Stack: FastAPI + SQLite (modo WAL).
Ejecución: uvicorn main:app --reload
"""

import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from auth import crear_sesion, eliminar_sesion, validar_sesion, verify_password
from database import create_tables, get_connection

INDEX_HTML = Path(__file__).resolve().parent / "index.html"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HORA_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_tables()
    yield


app = FastAPI(
    title="API de Citas - Clinica",
    description="Sistema de agendamiento de citas para una clinica de hasta 5 medicos.",
    version="1.0.0",
    lifespan=lifespan,
)

# Permite que la interfaz web funcione servida por el backend o desde otro origen
# (por ejemplo, abriendo index.html directamente desde el navegador).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- modelos
class AgendarRequest(BaseModel):
    bloque_id: int
    paciente_nombre: str = Field(min_length=2, max_length=120)
    paciente_telefono: str
    paciente_email: str = ""

    @field_validator("paciente_nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres.")
        return v

    @field_validator("paciente_telefono")
    @classmethod
    def _telefono(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or not (7 <= len(v) <= 15):
            raise ValueError("El telefono debe contener solo digitos (7 a 15).")
        return v

    @field_validator("paciente_email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = (v or "").strip()
        if v and not EMAIL_RE.match(v):
            raise ValueError("Email invalido.")
        return v


class CancelarRequest(BaseModel):
    id_cancelacion: Optional[str] = None
    cita_id: Optional[int] = None
    telefono: Optional[str] = None


class BloquearRequest(BaseModel):
    medico_id: int
    fecha: str
    hora_inicio: str
    hora_fin: str


class LoginRequest(BaseModel):
    usuario: str
    password: str


# ------------------------------------------------------- autenticación
def get_usuario_actual(
    authorization: Optional[str] = Header(None, description="Bearer <token>"),
) -> dict:
    """Dependencia que valida el token y devuelve el usuario de la sesión."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado.")
    token = authorization.removeprefix("Bearer ").strip()
    conn = get_connection()
    try:
        usuario = validar_sesion(conn, token)
    finally:
        conn.close()
    if not usuario:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada.")
    return usuario


@app.post("/api/auth/login")
def login(datos: LoginRequest):
    conn = get_connection()
    try:
        fila = conn.execute(
            "SELECT * FROM usuarios WHERE usuario = ?",
            (datos.usuario.strip(),),
        ).fetchone()
        if not fila or not verify_password(datos.password, fila["password_hash"]):
            raise HTTPException(
                status_code=401, detail="Usuario o contraseña incorrectos."
            )
        token = crear_sesion(conn, fila["id"])
        conn.commit()
    except HTTPException:
        raise
    finally:
        conn.close()

    return {
        "token": token,
        "usuario": fila["usuario"],
        "nombre": fila["nombre"],
        "rol": fila["rol"],
        "medico_id": fila["medico_id"],
    }


@app.get("/api/auth/me")
def auth_me(usuario: dict = Depends(get_usuario_actual)):
    return {
        "usuario": usuario["usuario"],
        "nombre": usuario["nombre"],
        "rol": usuario["rol"],
        "medico_id": usuario["medico_id"],
    }


@app.post("/api/auth/logout")
def logout(
    authorization: Optional[str] = Header(None),
    usuario: dict = Depends(get_usuario_actual),
):
    token = authorization.removeprefix("Bearer ").strip()
    conn = get_connection()
    try:
        eliminar_sesion(conn, token)
    finally:
        conn.close()
    return {"mensaje": "Sesión cerrada."}


# ---------------------------------------------------------------- endpoints
@app.get("/", include_in_schema=False)
def raiz():
    """Sirve la interfaz web (index.html) si existe."""
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    return {
        "app": "API de Citas - Clinica",
        "mensaje": "index.html no encontrado. Los endpoints de la API siguen disponibles.",
        "endpoints": [
            "GET  /api/medicos",
            "GET  /api/disponibilidad?medico_id={id}&fecha={YYYY-MM-DD}",
            "GET  /api/citas?id_cancelacion={codigo} | ?telefono={tel}",
            "GET  /api/citas?medico_id={id}&fecha_inicio={D}&fecha_fin={D}",
            "POST /api/agendar",
            "POST /api/cancelar",
            "POST /api/bloquear-hora",
        ],
    }


@app.get("/api/citas")
def consultar_citas(
    id_cancelacion: Optional[str] = Query(None, description="Codigo unico de cancelacion"),
    telefono: Optional[str] = Query(None, description="Telefono del paciente"),
    medico_id: Optional[int] = Query(None, description="Filtrar por medico"),
    fecha_inicio: Optional[str] = Query(None, description="Inicio del rango (YYYY-MM-DD)"),
    fecha_fin: Optional[str] = Query(None, description="Fin del rango (YYYY-MM-DD)"),
    usuario: dict = Depends(get_usuario_actual),
):
    """Consulta citas.

    - Por paciente: 'id_cancelacion' o 'telefono'.
    - Por agenda (vista de calendario): 'medico_id' (opcional) y/o rango
      'fecha_inicio'/'fecha_fin'.
    """
    es_busqueda_paciente = bool(id_cancelacion or telefono)
    es_agenda = bool(medico_id or fecha_inicio or fecha_fin)
    if not es_busqueda_paciente and not es_agenda:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar 'id_cancelacion' o 'telefono', o un rango de fechas.",
        )
    for f in (fecha_inicio, fecha_fin):
        if f is not None and not FECHA_RE.match(f):
            raise HTTPException(
                status_code=400, detail="Fecha invalida. Use YYYY-MM-DD."
            )
    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        raise HTTPException(
            status_code=400, detail="fecha_inicio no puede ser posterior a fecha_fin."
        )

    conn = get_connection()
    try:
        sql = (
            "SELECT c.id AS cita_id, c.bloque_id, c.paciente_nombre,"
            "       c.paciente_telefono, c.paciente_email, c.id_cancelacion,"
            "       c.fecha_creacion, b.medico_id, b.fecha, b.hora_inicio,"
            "       b.hora_fin, m.nombre AS medico, m.especialidad"
            " FROM citas c"
            " JOIN bloques_horarios b ON b.id = c.bloque_id"
            " JOIN medicos m ON m.id = b.medico_id"
        )
        if es_busqueda_paciente:
            if id_cancelacion:
                filas = conn.execute(
                    sql + " WHERE c.id_cancelacion = ?",
                    (id_cancelacion,),
                ).fetchall()
            else:
                filas = conn.execute(
                    sql + " WHERE c.paciente_telefono = ?"
                    " ORDER BY b.fecha, b.hora_inicio",
                    (telefono.strip(),),
                ).fetchall()
        else:
            condiciones = []
            params: list = []
            if medico_id:
                condiciones.append("b.medico_id = ?")
                params.append(medico_id)
            if fecha_inicio:
                condiciones.append("b.fecha >= ?")
                params.append(fecha_inicio)
            if fecha_fin:
                condiciones.append("b.fecha <= ?")
                params.append(fecha_fin)
            sql += " WHERE " + " AND ".join(condiciones)
            sql += " ORDER BY b.fecha, b.hora_inicio"
            filas = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    return {"citas": [dict(f) for f in filas], "total": len(filas)}


@app.get("/api/medicos")
def listar_medicos(usuario: dict = Depends(get_usuario_actual)):
    conn = get_connection()
    try:
        filas = conn.execute(
            "SELECT id, nombre, especialidad FROM medicos ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return {"medicos": [dict(f) for f in filas], "total": len(filas)}


@app.get("/api/disponibilidad")
def disponibilidad(
    medico_id: int = Query(..., description="Id del medico"),
    fecha: str = Query(..., description="Fecha en formato YYYY-MM-DD"),
    usuario: dict = Depends(get_usuario_actual),
):
    if not FECHA_RE.match(fecha):
        raise HTTPException(status_code=400, detail="Fecha invalida. Use YYYY-MM-DD.")

    conn = get_connection()
    try:
        medico = conn.execute(
            "SELECT id FROM medicos WHERE id = ?", (medico_id,)
        ).fetchone()
        if not medico:
            raise HTTPException(status_code=404, detail="Medico no encontrado.")

        filas = conn.execute(
            "SELECT id, fecha, hora_inicio, hora_fin, estado"
            " FROM bloques_horarios"
            " WHERE medico_id = ? AND fecha = ? AND estado = 'DISPONIBLE'"
            " ORDER BY hora_inicio",
            (medico_id, fecha),
        ).fetchall()
    finally:
        conn.close()

    return {
        "medico_id": medico_id,
        "fecha": fecha,
        "bloques": [dict(f) for f in filas],
        "total": len(filas),
    }


@app.post("/api/agendar", status_code=201)
def agendar(datos: AgendarRequest, usuario: dict = Depends(get_usuario_actual)):
    conn = get_connection()
    try:
        # BEGIN IMMEDIATE serializa los escritores: evita doble reserva concurrente.
        conn.execute("BEGIN IMMEDIATE")

        fila = conn.execute(
            "SELECT b.id, b.medico_id, b.fecha, b.hora_inicio, b.hora_fin,"
            "       b.estado, m.nombre AS medico"
            " FROM bloques_horarios b JOIN medicos m ON m.id = b.medico_id"
            " WHERE b.id = ?",
            (datos.bloque_id,),
        ).fetchone()
        if not fila:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Bloque no encontrado.")
        if fila["estado"] != "DISPONIBLE":
            conn.rollback()
            raise HTTPException(
                status_code=409, detail="El bloque ya no esta disponible."
            )

        cur = conn.execute(
            "UPDATE bloques_horarios SET estado = 'OCUPADO'"
            " WHERE id = ? AND estado = 'DISPONIBLE'",
            (datos.bloque_id,),
        )
        if cur.rowcount == 0:
            conn.rollback()
            raise HTTPException(
                status_code=409, detail="El bloque ya no esta disponible."
            )

        id_cancelacion = uuid.uuid4().hex
        cur = conn.execute(
            "INSERT INTO citas"
            " (bloque_id, paciente_nombre, paciente_telefono, paciente_email,"
            "  id_cancelacion, fecha_creacion)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                datos.bloque_id,
                datos.paciente_nombre,
                datos.paciente_telefono,
                datos.paciente_email,
                id_cancelacion,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        cita_id = cur.lastrowid
        conn.commit()
    except HTTPException:
        raise
    except sqlite3.Error as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {exc}")
    finally:
        conn.close()

    return {
        "mensaje": "Cita agendada correctamente.",
        "cita_id": cita_id,
        "id_cancelacion": id_cancelacion,
        "medico": fila["medico"],
        "fecha": fila["fecha"],
        "hora_inicio": fila["hora_inicio"],
        "hora_fin": fila["hora_fin"],
    }


@app.post("/api/cancelar")
def cancelar(datos: CancelarRequest, usuario: dict = Depends(get_usuario_actual)):
    if not datos.id_cancelacion and not (datos.cita_id and datos.telefono):
        raise HTTPException(
            status_code=400,
            detail="Debe enviar 'id_cancelacion' o ('cita_id' y 'telefono').",
        )

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")

        if datos.id_cancelacion:
            fila = conn.execute(
                "SELECT id, bloque_id, paciente_nombre, paciente_telefono"
                " FROM citas WHERE id_cancelacion = ?",
                (datos.id_cancelacion,),
            ).fetchone()
        else:
            fila = conn.execute(
                "SELECT id, bloque_id, paciente_nombre, paciente_telefono"
                " FROM citas WHERE id = ? AND paciente_telefono = ?",
                (datos.cita_id, (datos.telefono or "").strip()),
            ).fetchone()

        if not fila:
            conn.rollback()
            raise HTTPException(
                status_code=404,
                detail="Cita no encontrada. Verifique los datos enviados.",
            )

        # Elimina la cita y libera el bloque al instante, de forma atomica.
        conn.execute("DELETE FROM citas WHERE id = ?", (fila["id"],))
        conn.execute(
            "UPDATE bloques_horarios SET estado = 'DISPONIBLE' WHERE id = ?",
            (fila["bloque_id"],),
        )
        conn.commit()
    except HTTPException:
        raise
    except sqlite3.Error as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {exc}")
    finally:
        conn.close()

    return {
        "mensaje": "Cita cancelada. El bloque quedo DISPONIBLE nuevamente.",
        "cita_id": fila["id"],
        "paciente": fila["paciente_nombre"],
    }


@app.post("/api/bloquear-hora")
def bloquear_hora(datos: BloquearRequest, usuario: dict = Depends(get_usuario_actual)):
    if not FECHA_RE.match(datos.fecha):
        raise HTTPException(status_code=400, detail="Fecha invalida. Use YYYY-MM-DD.")
    if not (HORA_RE.match(datos.hora_inicio) and HORA_RE.match(datos.hora_fin)):
        raise HTTPException(status_code=400, detail="Horas invalidas. Use HH:MM.")
    if datos.hora_inicio >= datos.hora_fin:
        raise HTTPException(
            status_code=400, detail="hora_inicio debe ser anterior a hora_fin."
        )

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")

        medico = conn.execute(
            "SELECT id FROM medicos WHERE id = ?", (datos.medico_id,)
        ).fetchone()
        if not medico:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Medico no encontrado.")

        cur = conn.execute(
            "INSERT INTO bloques_horarios"
            " (medico_id, fecha, hora_inicio, hora_fin, estado)"
            " VALUES (?, ?, ?, ?, 'OCUPADO')",
            (datos.medico_id, datos.fecha, datos.hora_inicio, datos.hora_fin),
        )
        conn.commit()
    except HTTPException:
        raise
    except sqlite3.Error as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {exc}")
    finally:
        conn.close()

    return {
        "mensaje": "Bloque marcado como OCUPADO manualmente.",
        "bloque_id": cur.lastrowid,
        "medico_id": datos.medico_id,
        "fecha": datos.fecha,
        "hora_inicio": datos.hora_inicio,
        "hora_fin": datos.hora_fin,
    }


if __name__ == "__main__":
    import os

    import uvicorn

    puerto = int(os.environ.get("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=puerto)
