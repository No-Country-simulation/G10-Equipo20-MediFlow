"""Dependencias de FastAPI. Los tests las reemplazan (RN-U4)."""
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import abrir_sesion
from app.services.storage import Storage, StorageLocal, StorageOCI


def get_session() -> Iterator[Session]:
    yield from abrir_sesion()


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.oci_namespace and settings.oci_bucket:
        return StorageOCI(settings.oci_namespace, settings.oci_bucket, settings.oci_region or None)
    return StorageLocal(settings.storage_local_dir)
