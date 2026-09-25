import logging
from datetime import UTC, datetime
from typing import BinaryIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.models.document import Document
from app.repositories.documents import DocumentRepository
from app.schemas.document import DocumentResponse
from app.services.storage import DocumentStorage, LocalDocumentStorage
from app.services.validation import validate_content, validate_filename
from app.services.lifecycle import initialize_history, transition
from app.schemas.lifecycle import DocumentStatus
from app.services.errors import DocumentError

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self, repository: DocumentRepository, storage: DocumentStorage, max_bytes: int, country: str = "EC"):
        self.repository = repository
        self.storage = storage
        self.max_bytes = max_bytes
        self.country = country

    def ingest(self, filename: str | None, source: BinaryIO) -> DocumentResponse:
        document_id = uuid4()
        # El rechazo conserva solo una referencia auditable, nunca el binario invalido.
        display_name = (filename or "archivo_sin_nombre").replace("\\", "/").rsplit("/", 1)[-1]
        display_name = "".join(char for char in display_name if ord(char) >= 32)[:255] or "archivo_sin_nombre"
        document = Document(document_id=document_id, original_filename=display_name,
                            received_at=datetime.now(UTC), format=None, size_bytes=None, storage_key=None,
                            country=self.country, storage_backend=self.storage.backend, storage_bucket=self.storage.bucket)
        initialize_history(document)
        saved = False
        key = None
        try:
            name, expected_format = validate_filename(filename)
            extension = "jpg" if expected_format == "jpeg" else expected_format
            key = f"{document_id}.{extension}"
            with TemporaryDirectory(prefix="mediflow-upload-") as temporary:
                path, size = LocalDocumentStorage(Path(temporary)).save(key, source, self.max_bytes)
                document.size_bytes = size
                detected = validate_content(path, expected_format, size)
                if self.storage.backend == "r2":
                    key = f"{self.country}/originals/{key}"
                self.storage.put_file(key, path, self.max_bytes)
                saved = True
            document.original_filename = name
            document.format = detected
            document.storage_key = key
            transition(document, DocumentStatus.VALIDADO, "FILE_VALIDATED")
            self.repository.add(document)
            response = DocumentResponse.model_validate(document)
            self.repository.commit()
            return response
        except DocumentError as exc:
            self.repository.rollback()
            if saved:
                self.storage.delete(key)
            document.storage_key = None
            document.rejection_reason = exc.detail[:255]
            transition(document, DocumentStatus.RECHAZADO, "FILE_REJECTED")
            try:
                self.repository.add(document)
                self.repository.commit()
            except Exception:
                self.repository.rollback()
                raise
            raise DocumentError(exc.status_code, exc.detail, document_id) from None
        except Exception:
            try:
                self.repository.rollback()
            finally:
                if saved:
                    try:
                        self.storage.delete(key)
                    except OSError:
                        logger.error("No se pudo limpiar el archivo de documento %s", document_id)
            raise
