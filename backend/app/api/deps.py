"""Dependencias de FastAPI. Los tests las reemplazan (RN-U4)."""
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import abrir_sesion
from app.core.sesiones import cuenta_de_la_sesion
from app.models.gobierno import Usuario
from app.services.llm import ClienteGemini, ClienteLLM, ClienteOpenAI, ErrorTransitorioLLM, LlamadaLLM, RespuestaLLM
from app.services.storage import Storage, StorageLocal, StorageOCI


def get_session() -> Iterator[Session]:
    yield from abrir_sesion()


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.oci_namespace and settings.oci_bucket:
        return StorageOCI(settings.oci_namespace, settings.oci_bucket, settings.oci_region or None)
    return StorageLocal(settings.storage_local_dir)


class ClienteNoConfigurado:
    """Sin OPENAI_API_KEY el pipeline sigue la ruta de fallo técnico (RN-P2, RN-P4)."""

    def completar_estructurado(self, llamada: LlamadaLLM) -> RespuestaLLM:
        raise ErrorTransitorioLLM("OPENAI_API_KEY no configurada")


@lru_cache
def get_llm() -> ClienteLLM:
    settings = get_settings()
    if settings.llm_proveedor == "gemini" and settings.gemini_api_key:
        return ClienteGemini()
    if settings.llm_proveedor == "openai" and settings.openai_api_key:
        return ClienteOpenAI()
    return ClienteNoConfigurado()


# --- Sesión y firma (RN-K1, RN-K2, RN-K5) ---------------------------------------------------------

ROLES_CLINICOS = ("auditor_clinico", "quimico_farmaceutico", "auditor_autorizaciones", "jefe_urgencias")


def cuenta_actual(request: Request, session: Session = Depends(get_session)) -> Usuario | None:
    """La cuenta que inició sesión, o None si la petición es anónima."""
    return cuenta_de_la_sesion(request, session)


def acceso(*roles: str) -> Callable[..., None]:
    """Dependencia de un router: exige sesión si la instalación lo pide y, con sesión, que el rol sea de los permitidos (RN-K2)."""

    def verificar(cuenta: Usuario | None = Depends(cuenta_actual)) -> None:
        if cuenta is None:
            if get_settings().exigir_sesion:
                raise HTTPException(status_code=401, detail="sesion_requerida")
            return
        if roles and cuenta.rol not in roles:
            raise HTTPException(status_code=403, detail=f"RN-K2: el rol {cuenta.rol} no accede a esta sección. "
                                                        "Quien configura no revisa; quien administra no ve datos clínicos")

    return verificar


@dataclass(frozen=True)
class Firmante:
    usuario: str
    rol: str | None
    autenticado: bool


def firmante(session: Session, cuenta: Usuario | None, declarado: str | None, rol_declarado: str | None = None) -> Firmante:
    """Quién firma la acción. Con sesión firma la cuenta, no lo que venga escrito en la petición (RN-G4, RN-Q5).
    Sin sesión firma el nombre declarado, salvo que ese nombre sea una cuenta con clave: esa solo firma con su sesión (RN-K5)."""
    if cuenta is not None:
        return Firmante(cuenta.usuario, cuenta.rol, True)
    nombre = (declarado or "").strip()
    registrado = session.scalars(select(Usuario).where(Usuario.usuario == nombre)).first() if nombre else None
    if registrado is not None and registrado.clave_hash:
        raise HTTPException(status_code=401, detail=f"RN-K5: la cuenta {nombre} tiene clave; inicia sesión para firmar con ella")
    return Firmante(nombre, rol_declarado, False)
