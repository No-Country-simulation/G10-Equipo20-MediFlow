"""Dependencias de FastAPI. Los tests las reemplazan (RN-U4)."""
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import abrir_sesion
from app.graph.memoria import crear_memoria
from app.core.sesiones import cuenta_de_la_sesion
from app.models.gobierno import Usuario
from app.services.errores import ErrorDeRevision
from app.services.llm import ClienteGemini, ClienteLLM, ClienteOpenAI, ErrorTransitorioLLM, LlamadaLLM, RespuestaLLM
from app.services.usuarios import ServicioUsuarios
from app.services.storage import Storage, StorageLocal, StorageOCI, StorageR2


def get_session() -> Iterator[Session]:
    yield from abrir_sesion()


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend.strip().lower() == "r2":
        return StorageR2(endpoint_url=settings.r2_endpoint_url, access_key_id=settings.r2_access_key_id,
                         secret_access_key=settings.r2_secret_access_key, bucket=settings.r2_bucket_name,
                         prefijo=settings.r2_prefijo, region=settings.r2_region)
    if settings.oci_namespace and settings.oci_bucket:
        return StorageOCI(settings.oci_namespace, settings.oci_bucket, settings.oci_region or None)
    return StorageLocal(settings.storage_local_dir)


@lru_cache
def get_memoria():
    """Memoria del grafo en la misma base PostgreSQL (RN-P2, RN-I4)."""
    return crear_memoria(get_settings().database_url)


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
    """Dependencia de un router: exige sesión (RN-K5) y que el rol de la cuenta sea de los permitidos (RN-K2)."""

    def verificar(cuenta: Usuario | None = Depends(cuenta_actual)) -> None:
        if cuenta is None:
            raise HTTPException(status_code=401, detail="sesion_requerida")
        if cuenta.debe_cambiar_clave:
            raise HTTPException(status_code=403, detail="cambio_de_clave_requerido")
        if roles and cuenta.rol not in roles:
            raise HTTPException(status_code=403, detail=f"RN-K2: el rol {cuenta.rol} no accede a esta sección. "
                                                        "Quien configura no revisa; quien administra no ve datos clínicos")

    return verificar


@dataclass(frozen=True)
class Firmante:
    usuario: str
    rol: str


def firmante(session: Session, cuenta: Usuario | None, accion: str) -> Firmante:
    """Quién firma la acción: siempre la cuenta de la sesión (RN-G4, RN-Q5), si su estado, su tipo y su rol se lo
    permiten (RN-K4, RN-K5, RN-K2). No existe firma por nombre escrito."""
    if cuenta is None:
        raise HTTPException(status_code=401, detail="sesion_requerida")
    try:
        ServicioUsuarios(session).validar_cuenta(cuenta, accion)
    except ErrorDeRevision as error:
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
    return Firmante(cuenta.usuario, cuenta.rol)
