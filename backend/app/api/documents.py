from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.repositories.documents import DocumentRepository
from app.schemas.document import DocumentResponse
from app.services.documents import DocumentService
from app.services.errors import DocumentError
from app.services.storage import LocalDocumentStorage

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=201)
def upload_document(
    file: Annotated[UploadFile, File(description="Documento PDF, JPG o PNG")],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentResponse:
    service = DocumentService(
        DocumentRepository(session), LocalDocumentStorage(settings.documents_dir),
        settings.max_upload_bytes,
    )
    try:
        return service.ingest(file.filename, file.file)
    except DocumentError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(503, "No fue posible guardar el documento. Intenta nuevamente.") from exc


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> DocumentResponse:
    try:
        document = DocumentRepository(session).get(document_id)
    except SQLAlchemyError as exc:
        raise HTTPException(503, "No fue posible consultar el documento.") from exc
    if document is None:
        raise HTTPException(404, "Documento no encontrado.")
    return DocumentResponse.model_validate(document)
