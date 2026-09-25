import base64
import json
import subprocess
import sys
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query, Response
from sqlalchemy import select, func
from app.models.document import Document
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.repositories.documents import DocumentRepository
from app.schemas.document import DocumentResponse, DocumentList
from app.services.documents import DocumentService
from app.services.errors import DocumentError
from app.services.storage import get_storage
from app.providers.base import DocumentProvider, ProviderError
from app.providers.gemini import GeminiProvider
from app.schemas.processing import ProcessingResult
from app.services.processing import process_document
from app.schemas.lifecycle import DocumentStatus, StateEvent
from app.schemas.processing import ReviewRequest, ReviewAudit
from app.services.review import review_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/{document_id}/review", response_model=ProcessingResult)
def submit_review(document_id: UUID, request: ReviewRequest,
                  session: Annotated[Session, Depends(get_session)],
                  settings: Annotated[Settings, Depends(get_settings)]):
    try:
        return review_document(document_id, request, session, settings)
    except DocumentError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(503, "REVIEW_STORAGE_UNAVAILABLE") from None


@router.get("/{document_id}/reviews", response_model=list[ReviewAudit])
def get_reviews(document_id: UUID, session: Annotated[Session, Depends(get_session)]):
    try:
        document = DocumentRepository(session).get(document_id)
    except SQLAlchemyError:
        raise HTTPException(503, "REVIEW_STORAGE_UNAVAILABLE") from None
    if document is None:
        raise HTTPException(404, "DOCUMENT_NOT_FOUND")
    return document.review_history


def get_document_provider(settings: Annotated[Settings, Depends(get_settings)]) -> DocumentProvider:
    return GeminiProvider(settings)


@router.post("", response_model=DocumentResponse, status_code=201)
def upload_document(
    file: Annotated[UploadFile, File(description="Documento PDF, JPG o PNG")],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentResponse:
    try:
        service = DocumentService(DocumentRepository(session), get_storage(settings),
                                  settings.max_upload_bytes, settings.default_country)
        return service.ingest(file.filename, file.file)
    except DocumentError as exc:
        detail = {"message": exc.detail, "status": DocumentStatus.RECHAZADO,
                  "document_id": str(exc.document_id)} if exc.document_id else exc.detail
        raise HTTPException(exc.status_code, detail) from None
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(503, "No fue posible guardar el documento. Intenta nuevamente.") from exc


@router.get("", response_model=DocumentList)
def list_documents(
    session: Annotated[Session, Depends(get_session)],
    status: DocumentStatus | None = None,
    q: Annotated[str, Query(max_length=255)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentList:
    query = select(Document)
    if status is not None:
        query = query.where(Document.status == status.value)
    if q.strip():
        query = query.where(Document.original_filename.icontains(q.strip(), autoescape=True))
    try:
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(query.order_by(Document.received_at.desc(), Document.document_id.desc()).limit(limit).offset(offset))
        return DocumentList(items=[DocumentResponse.model_validate(row) for row in rows], total=total, limit=limit, offset=offset)
    except SQLAlchemyError:
        raise HTTPException(503, "DOCUMENT_LIST_UNAVAILABLE") from None


@router.get("/{document_id}/preview")
def preview_pdf(document_id: UUID, session: Annotated[Session, Depends(get_session)],
                settings: Annotated[Settings, Depends(get_settings)],
                page: Annotated[int, Query(ge=1)] = 1) -> Response:
    try:
        document = DocumentRepository(session).get(document_id)
        if document is None or not document.storage_key:
            raise HTTPException(404, "DOCUMENT_FILE_NOT_FOUND")
        if document.format != "pdf":
            raise HTTPException(415, "PREVIEW_REQUIRES_PDF")
        with get_storage(settings, document.storage_backend, document.storage_bucket).materialize(document.storage_key, settings.max_upload_bytes) as path:
            process = subprocess.run([sys.executable, "-m", "app.services.pdf_preview", str(path), str(page)],
                                     capture_output=True, check=True, timeout=settings.pdf_timeout_seconds)
            result = json.loads(process.stdout)
        if result.get("error"):
            raise HTTPException(404 if result["error"] == "PAGE_NOT_FOUND" else 422, result["error"])
        return Response(base64.b64decode(result["image"]), media_type="image/png",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                 "X-Page-Count": str(result["pages"])})
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "PDF_PREVIEW_TIMEOUT") from None
    except (subprocess.CalledProcessError, ValueError):
        raise HTTPException(422, "PDF_CONTENT_UNREADABLE") from None
    except DocumentError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None
    except (SQLAlchemyError, OSError):
        raise HTTPException(503, "DOCUMENT_STORAGE_UNAVAILABLE") from None


@router.get("/{document_id}/file")
def get_original(document_id: UUID, session: Annotated[Session, Depends(get_session)],
                 settings: Annotated[Settings, Depends(get_settings)]) -> Response:
    try:
        document = DocumentRepository(session).get(document_id)
        if document is None or document.storage_key is None:
            raise HTTPException(404, "DOCUMENT_FILE_NOT_FOUND")
        with get_storage(settings, document.storage_backend, document.storage_bucket).materialize(document.storage_key, settings.max_upload_bytes) as path:
            data = path.read_bytes()
        return Response(data, media_type={"pdf": "application/pdf", "png": "image/png", "jpeg": "image/jpeg"}[document.format],
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                 "Content-Disposition": f'inline; filename="{document_id}.{document.format}"'})
    except DocumentError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None
    except (SQLAlchemyError, OSError):
        raise HTTPException(503, "DOCUMENT_STORAGE_UNAVAILABLE") from None


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


@router.post("/{document_id}/process", response_model=ProcessingResult)
def process_uploaded_document(
    document_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[DocumentProvider, Depends(get_document_provider)],
) -> ProcessingResult:
    try:
        return process_document(document_id, session, settings, provider)
    except DocumentError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None
    except ProviderError as exc:
        raise HTTPException(exc.http_status, exc.code) from None
    except (SQLAlchemyError, OSError):
        session.rollback()
        raise HTTPException(503, "PROCESSING_STORAGE_UNAVAILABLE") from None


@router.get("/{document_id}/result", response_model=ProcessingResult)
def get_processing_result(
    document_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> ProcessingResult:
    try:
        document = DocumentRepository(session).get(document_id)
    except SQLAlchemyError:
        raise HTTPException(503, "RESULT_STORAGE_UNAVAILABLE") from None
    if document is None:
        raise HTTPException(404, "DOCUMENT_NOT_FOUND")
    if document.processing_result is None:
        raise HTTPException(409, "DOCUMENT_NOT_PROCESSED")
    return ProcessingResult.model_validate(document.processing_result)


@router.get("/{document_id}/history", response_model=list[StateEvent])
def get_document_history(
    document_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> list[StateEvent]:
    try:
        document = DocumentRepository(session).get(document_id)
    except SQLAlchemyError:
        raise HTTPException(503, "HISTORY_STORAGE_UNAVAILABLE") from None
    if document is None:
        raise HTTPException(404, "DOCUMENT_NOT_FOUND")
    return [StateEvent.model_validate(event) for event in document.state_history]
