from pathlib import Path
import os
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
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        filename = Path(key).name
        if not filename or filename in (".", ".."):
            raise ValueError(f"Invalid storage key: {key}")
        return self.directory / filename

    def save(self, key: str, source: BinaryIO, max_bytes: int) -> tuple[Path, int]:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        path.unlink(missing_ok=True)
        size = 0
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
        try:
            self._path(key).unlink(missing_ok=True)
        except Exception:
            pass

    def local_path(self, key: str) -> Path:
        return self._path(key)

    def put_file(self, key: str, path: Path, max_bytes: int) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
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
    selected = backend or settings.storage_backend
    r2_configured = bool(
        getattr(settings, "r2_bucket_name", None)
        and getattr(settings, "r2_endpoint_url", None)
        and hasattr(settings, "r2_access_key_id") and settings.r2_access_key_id.get_secret_value()
        and hasattr(settings, "r2_secret_access_key") and settings.r2_secret_access_key.get_secret_value()
    )
    if selected == "r2" and r2_configured:
        from app.services.r2_storage import R2DocumentStorage
        return R2DocumentStorage(settings, bucket)

    docs_dir = getattr(settings, "documents_dir", None) or Path("/tmp/mediflow-documents")
    return LocalDocumentStorage(docs_dir)
