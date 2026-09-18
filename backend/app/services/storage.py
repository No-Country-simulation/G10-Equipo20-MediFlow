from pathlib import Path
from typing import BinaryIO, Protocol

from app.services.errors import DocumentError


class DocumentStorage(Protocol):
    def save(self, key: str, source: BinaryIO, max_bytes: int) -> tuple[Path, int]: ...
    def delete(self, key: str) -> None: ...


class LocalDocumentStorage:
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
