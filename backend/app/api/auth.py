"""Inicio y cierre de sesión del personal (RN-K5). Las cuentas las crea el administrador en /administracion."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import cuenta_actual, get_session
from app.core.config import get_settings
from app.core.sesiones import abrir_sesion, cerrar_sesion, clave_coincide
from app.models.gobierno import Usuario
from app.services.usuarios import ServicioUsuarios

router = APIRouter(prefix="/auth", tags=["sesion"])


class Credenciales(BaseModel):
    usuario: str = Field(..., min_length=1, max_length=128)
    clave: str = Field(..., min_length=1, max_length=128)


def _cuenta(u: Usuario) -> dict:
    return {"usuario": u.usuario, "nombre": u.nombre, "rol": u.rol}


@router.post("/ingresar")
def ingresar(cuerpo: Credenciales, request: Request, response: Response, session: Session = Depends(get_session)):
    u = ServicioUsuarios(session).buscar(cuerpo.usuario)
    # El mismo mensaje para usuario desconocido, clave equivocada, cuenta sin clave o desactivada: no se revela cuál fue.
    if u is None or not u.activo or not clave_coincide(cuerpo.clave, u.clave_hash):
        raise HTTPException(status_code=401, detail="Usuario o clave incorrectos")
    abrir_sesion(u, session, response, request)
    return _cuenta(u)


@router.get("/estado")
def estado(cuenta: Usuario | None = Depends(cuenta_actual)):
    """Lo que la interfaz necesita para decidir si muestra el inicio de sesión."""
    return {"exigir_sesion": get_settings().exigir_sesion, "sesion": _cuenta(cuenta) if cuenta else None}


@router.post("/salir")
def salir(request: Request, response: Response, session: Session = Depends(get_session)):
    cerrar_sesion(session, response, request)
    return {"sesion": None}
