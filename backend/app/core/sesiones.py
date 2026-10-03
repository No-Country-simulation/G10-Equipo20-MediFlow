"""Cuentas con clave y sesiones del personal (RN-K5, RN-Q5, RN-G4).

La clave se guarda como hash PBKDF2-SHA256 con sal propia; la sesión viaja en una cookie HttpOnly
y en la base solo queda el hash del token, así un volcado de la base no sirve para entrar.
La cookie es SameSite=Lax y la API solo recibe JSON sin CORS, de modo que otro sitio no puede
firmar acciones con la sesión de un usuario.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.gobierno import SesionUsuario, Usuario

COOKIE = "mediflow_sesion"
DURACION_S = 8 * 60 * 60  # un turno
ITERACIONES = 600_000
_ALGORITMO = "pbkdf2_sha256"


def hash_clave(clave: str) -> str:
    sal = secrets.token_bytes(16)
    resumen = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, ITERACIONES)
    return f"{_ALGORITMO}${ITERACIONES}${sal.hex()}${resumen.hex()}"


def clave_coincide(clave: str, guardado: str | None) -> bool:
    try:
        algoritmo, iteraciones, sal, esperado = (guardado or "").split("$")
        if algoritmo != _ALGORITMO:
            return False
        obtenido = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), int(iteraciones))
        return hmac.compare_digest(obtenido, bytes.fromhex(esperado))
    except (ValueError, TypeError):
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def abrir_sesion(usuario: Usuario, session: Session, response: Response, request: Request) -> None:
    token = secrets.token_urlsafe(32)
    session.add(SesionUsuario(token_hash=_hash_token(token), usuario_id=usuario.id, expira_en=_ahora() + timedelta(seconds=DURACION_S)))
    session.commit()
    response.set_cookie(COOKIE, token, max_age=DURACION_S, httponly=True, samesite="lax", secure=_es_https(request), path="/")
    response.headers["Cache-Control"] = "no-store"


def _es_https(request: Request) -> bool:
    """Detrás de un proxy (nginx, balanceador) la API ve http; el proxy declara el esquema real."""
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower() == "https"


def cerrar_sesion(session: Session, response: Response, request: Request) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        session.execute(delete(SesionUsuario).where(SesionUsuario.token_hash == _hash_token(token)))
        session.commit()
    response.delete_cookie(COOKIE, path="/")


def cerrar_sesiones_de(usuario: Usuario, session: Session) -> None:
    """RN-K4: quien se desactiva, o cambia de clave, pierde de inmediato las sesiones abiertas."""
    session.execute(delete(SesionUsuario).where(SesionUsuario.usuario_id == usuario.id))


def cuenta_de_la_sesion(request: Request, session: Session) -> Usuario | None:
    """El usuario de la cookie, si la sesión existe, no venció y la cuenta sigue activa."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    registro = session.get(SesionUsuario, _hash_token(token))
    if registro is None:
        return None
    expira = registro.expira_en if registro.expira_en.tzinfo else registro.expira_en.replace(tzinfo=timezone.utc)
    if expira < _ahora():
        session.delete(registro)
        session.commit()
        return None
    usuario = session.get(Usuario, registro.usuario_id)
    return usuario if usuario is not None and usuario.activo else None
