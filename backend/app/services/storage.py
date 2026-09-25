"""Almacenamiento de originales y resultados (RN-G1, RN-P1).

En el MVP es un solo bucket con prefijo por país. `StorageLocal` sirve para
desarrollo y tests; `StorageOCI` usa OCI Object Storage (capa Always Free).
"""
from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def guardar(self, ruta: str, contenido: bytes, content_type: str = "application/octet-stream") -> None: ...

    def leer(self, ruta: str) -> bytes: ...


class StorageLocal:
    def __init__(self, directorio_base: Path | str):
        self.base = Path(directorio_base).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _resolver(self, ruta: str) -> Path:
        destino = (self.base / ruta).resolve()
        if self.base not in destino.parents and destino != self.base:
            raise ValueError(f"Ruta fuera del bucket: {ruta}")
        return destino

    def guardar(self, ruta: str, contenido: bytes, content_type: str = "application/octet-stream") -> None:
        destino = self._resolver(ruta)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)

    def leer(self, ruta: str) -> bytes:
        return self._resolver(ruta).read_bytes()


class StorageOCI:
    """OCI Object Storage. El SDK se importa al usarse para no exigirlo en tests (RN-U4)."""

    def __init__(self, namespace: str, bucket: str, region: str | None = None):
        import oci  # noqa: PLC0415

        config = oci.config.from_file()
        if region:
            config["region"] = region
        self._cliente = oci.object_storage.ObjectStorageClient(config)
        self.namespace = namespace
        self.bucket = bucket

    def guardar(self, ruta: str, contenido: bytes, content_type: str = "application/octet-stream") -> None:
        self._cliente.put_object(self.namespace, self.bucket, ruta, contenido, content_type=content_type)

    def leer(self, ruta: str) -> bytes:
        return self._cliente.get_object(self.namespace, self.bucket, ruta).data.content


CONTENT_TYPES = {"txt": "text/plain; charset=utf-8", "pdf": "application/pdf", "json": "application/json"}
