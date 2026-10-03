"""Sesión del personal (RN-K5): ingreso, salida, primer administrador de la instalación (RN-S3), clave propia
y registro de eventos de sesión (RN-K3, RN-G4). Las demás cuentas las crea el administrador en /administracion."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import cuenta_actual, get_session
from app.core.config import get_settings
from app.core.sesiones import abrir_sesion, cerrar_sesion, cerrar_sesiones_de, clave_coincide, hash_clave
from app.models.gobierno import Usuario
from app.services.errores import ErrorDeRevision
from app.services.usuarios import ServicioUsuarios, validar_clave

router = APIRouter(prefix="/auth", tags=["sesion"])

# El mismo mensaje para usuario desconocido, clave equivocada, cuenta sin clave, desactivada o bloqueada: no se revela cuál fue.
MENSAJE_CREDENCIALES = "Usuario o clave incorrectos"


class Credenciales(BaseModel):
    usuario: str = Field(..., min_length=1, max_length=128)
    clave: str = Field(..., min_length=1, max_length=128)


class PrimerAdministrador(BaseModel):
    usuario: str = Field(..., min_length=1, max_length=128)
    nombre: str = Field(..., min_length=1, max_length=256)
    clave: str = Field(..., min_length=1, max_length=128)


class CambioDeClave(BaseModel):
    clave_actual: str = Field(..., min_length=1, max_length=128)
    clave_nueva: str = Field(..., min_length=1, max_length=128)


def _cuenta(u: Usuario) -> dict:
    return {"usuario": u.usuario, "nombre": u.nombre, "rol": u.rol, "debe_cambiar_clave": bool(u.debe_cambiar_clave)}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _utc(momento: datetime) -> datetime:
    return momento if momento.tzinfo is not None else momento.replace(tzinfo=timezone.utc)


def _error(error: ErrorDeRevision) -> HTTPException:
    return HTTPException(status_code=error.codigo, detail=error.detalle)


@router.get("/roles")
def roles(session: Session = Depends(get_session)):
    """Tabla K como datos: el frontend arma el menú y el comportamiento de cada rol desde aquí (RN-K1). Público:
    no lleva nada clínico ni personal."""
    return [r.como_dict() for r in ServicioUsuarios(session).roles()]


@router.get("/estado")
def estado(cuenta: Usuario | None = Depends(cuenta_actual), session: Session = Depends(get_session)):
    """Lo que la interfaz necesita para decidir qué mostrar: ingreso, primer administrador o cambio de clave."""
    settings = get_settings()
    return {
        "sesion": _cuenta(cuenta) if cuenta else None,
        "sin_cuentas": not ServicioUsuarios(session).hay_cuentas(),
        "nombre_sede": settings.nombre_sede,
    }


@router.post("/primer_administrador", status_code=201)
def primer_administrador(cuerpo: PrimerAdministrador, request: Request, response: Response, session: Session = Depends(get_session)):
    """RN-S3: la instalación arranca sin cuentas; la primera, de administrador, se crea desde la pantalla de ingreso.
    Solo existe mientras no haya ninguna cuenta. Quien la crea elige su clave, así que no tiene que cambiarla."""
    servicio = ServicioUsuarios(session)
    if servicio.hay_cuentas():
        raise HTTPException(status_code=409, detail="la instalación ya tiene cuentas; las crea el administrador desde Administración")
    try:
        validar_clave(cuerpo.clave, cuerpo.usuario)
        u = servicio.crear(usuario=cuerpo.usuario, nombre=cuerpo.nombre, rol="administrador", tipo="persona", actor="instalacion")
    except ErrorDeRevision as error:
        raise _error(error) from error
    u.clave_hash = hash_clave(cuerpo.clave)
    u.debe_cambiar_clave = False
    u.ultimo_ingreso_en = _ahora()
    servicio.registrar_evento(u.usuario, "primer_administrador", "cuenta inicial de la instalación")
    abrir_sesion(u, session, response, request)
    return _cuenta(u)


@router.post("/ingresar")
def ingresar(cuerpo: Credenciales, request: Request, response: Response, session: Session = Depends(get_session)):
    settings = get_settings()
    servicio = ServicioUsuarios(session)
    u = servicio.buscar(cuerpo.usuario)
    ahora = _ahora()
    if u is not None and u.bloqueado_hasta is not None and _utc(u.bloqueado_hasta) > ahora:
        servicio.registrar_evento(u.usuario, "bloqueada", "intento durante el bloqueo")
        session.commit()
        raise HTTPException(status_code=401, detail=MENSAJE_CREDENCIALES)
    if u is None or not u.activo or not clave_coincide(cuerpo.clave, u.clave_hash):
        if u is None:
            servicio.registrar_evento(cuerpo.usuario.strip()[:128], "fallo", "usuario desconocido")
        else:
            u.intentos_fallidos = (u.intentos_fallidos or 0) + 1
            if u.intentos_fallidos >= settings.intentos_maximos:
                # RN-K4 en espíritu: la cuenta queda cerrada un rato; el mensaje al frente no cambia.
                u.bloqueado_hasta = ahora + timedelta(minutes=settings.bloqueo_min)
                u.intentos_fallidos = 0
                servicio.registrar_evento(u.usuario, "bloqueo", f"{settings.intentos_maximos} intentos fallidos; cuenta bloqueada {settings.bloqueo_min} min")
            else:
                servicio.registrar_evento(u.usuario, "fallo", "clave incorrecta" if u.activo else "cuenta desactivada")
        session.commit()
        raise HTTPException(status_code=401, detail=MENSAJE_CREDENCIALES)
    u.intentos_fallidos = 0
    u.bloqueado_hasta = None
    u.ultimo_ingreso_en = ahora
    servicio.registrar_evento(u.usuario, "ingreso", "")
    abrir_sesion(u, session, response, request)
    return _cuenta(u)


@router.post("/clave")
def cambiar_mi_clave(cuerpo: CambioDeClave, request: Request, response: Response, session: Session = Depends(get_session),
                     cuenta: Usuario | None = Depends(cuenta_actual)):
    """La propia clave, con la actual en mano. Cierra las demás sesiones de la cuenta y deja esta abierta."""
    if cuenta is None:
        raise HTTPException(status_code=401, detail="sesion_requerida")
    if not clave_coincide(cuerpo.clave_actual, cuenta.clave_hash):
        raise HTTPException(status_code=401, detail="la clave actual no coincide")
    try:
        validar_clave(cuerpo.clave_nueva, cuenta.usuario)
    except ErrorDeRevision as error:
        raise _error(error) from error
    cuenta.clave_hash = hash_clave(cuerpo.clave_nueva)
    cuenta.debe_cambiar_clave = False
    cerrar_sesiones_de(cuenta, session)
    ServicioUsuarios(session).registrar_evento(cuenta.usuario, "cambio_clave", "clave cambiada por su dueño")
    abrir_sesion(cuenta, session, response, request)
    return _cuenta(cuenta)


@router.post("/salir")
def salir(request: Request, response: Response, session: Session = Depends(get_session), cuenta: Usuario | None = Depends(cuenta_actual)):
    if cuenta is not None:
        ServicioUsuarios(session).registrar_evento(cuenta.usuario, "salida", "")
    cerrar_sesion(session, response, request)
    return {"sesion": None}
