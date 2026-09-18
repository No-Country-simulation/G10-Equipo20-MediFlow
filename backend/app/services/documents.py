import logging
from datetime import UTC, datetime
from typing import BinaryIO
from uuid import uuid4

from app.models.document import Document
from app.repositories.documents import DocumentRepository
from app.schemas.document import DocumentResponse
from app.services.storage import DocumentStorage
from app.services.validation import validate_content, validate_filename

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self, repository: DocumentRepository, storage: DocumentStorage, max_bytes: int):
        self.repository = repository
        self.storage = storage
        self.max_bytes = max_bytes

    def ingest(self, filename: str | None, source: BinaryIO) -> DocumentResponse:
        name, expected_format = validate_filename(filename)
        document_id = uuid4()
        extension = "jpg" if expected_format == "jpeg" else expected_format
        key = f"{document_id}.{extension}"
        saved = False
        try:
            path, size = self.storage.save(key, source, self.max_bytes)
            saved = True
            detected = validate_content(path, expected_format, size)
            document = Document(
                document_id=document_id, original_filename=name, format=detected,
                size_bytes=size, received_at=datetime.now(UTC), status="UPLOADED",
                storage_key=key,
            )
            self.repository.add(document)
            response = DocumentResponse.model_validate(document)
            self.repository.commit()
            return response
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
