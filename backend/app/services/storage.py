from pathlib import Path
from contextlib import AbstractContextManager, contextmanager
from collections.abc import Iterator
from typing import BinaryIO, Protocol

from app.services.errors import DocumentError


class DocumentStorage(Protocol):
    backend: str
    bucket: str | None
    def delete(self, key: str) -> None: ...
    def put_file(self, key: str, path: Path, max_bytes: int) -> None: ...
    def materialize(self, key: str, max_bytes: int) -> AbstractContextManager[Path]: ...


class LocalDocumentStorage:
    backend = "local"
    bucket = None

    def __init__(self, directory: Path):
        self.directory = directory

    def _path(self, key: str) -> Path:
        # Las claves las genera el servidor; no aceptar rutas externas.
        if not key or Path(key).name != key or "/" in key or "\\" in key:
            raise ValueError("Invalid storage key")
        return self.directory / key

    def save(self, key: str, source: BinaryIO, max_bytes: int) -> tuple[Path, int]:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        size = 0
        # Abrir fuera del try evita eliminar un archivo previo ante una colision.
        target = path.open("xb")
        try:
            with target:
                while chunk := source.read(64 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise DocumentError(413, "El archivo supera el limite permitido.")
                    target.write(chunk)
            return path, size
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def local_path(self, key: str) -> Path:
        return self._path(key)

    def put_file(self, key: str, path: Path, max_bytes: int) -> None:
        with path.open("rb") as source:
            self.save(key, source, max_bytes)

    @contextmanager
    def materialize(self, key: str, max_bytes: int) -> Iterator[Path]:
        path = self.local_path(key)
        if not path.is_file():
            raise DocumentError(422, "DOCUMENT_FILE_MISSING")
        if path.stat().st_size > max_bytes:
            raise DocumentError(413, "PROCESSING_FILE_TOO_LARGE")
        yield path


def get_storage(settings, backend=None, bucket=None):
    if (backend or settings.storage_backend) == "local":
        return LocalDocumentStorage(settings.documents_dir)
    from app.services.r2_storage import R2DocumentStorage
    return R2DocumentStorage(settings, bucket)
