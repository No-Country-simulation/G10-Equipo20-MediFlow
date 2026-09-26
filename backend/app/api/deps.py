"""Dependencias de FastAPI. Los tests las reemplazan (RN-U4)."""
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import abrir_sesion
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
