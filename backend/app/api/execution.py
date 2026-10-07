from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.auth import require_staff, require_permission, require_superadmin, same_origin
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.countries import COUNTRY_CODES
from app.core.document_catalog import REQUIRED_GROUPS, document_catalog
from app.models.execution import ProcessingJob, DocumentPolicy, ResultBackup
from app.repositories.documents import DocumentRepository
from app.schemas.document import DocumentResponse
from app.services.documents import DocumentService
from app.services.documentary_policy import PolicyInput
from app.services.errors import DocumentError
from app.services.jobs import enqueue
from app.services.storage import get_storage

router = APIRouter(tags=["processing"], dependencies=[Depends(require_staff), Depends(same_origin)])
Db = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]


class TextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=200000)
    country: str = "EC"
    origin_channel: str = Field(default="MANUAL", min_length=1, max_length=100)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    active_node: str | None
    completed_nodes: list[str]
    provider_calls: dict[str, int]
    attempt: int
    error_code: str | None


@router.post("/documents/text", response_model=DocumentResponse, status_code=201,
             dependencies=[Depends(require_permission("DOCUMENTS_UPLOAD"))])
def ingest_text(request: TextInput, session: Db, settings: Config):
    if request.country not in COUNTRY_CODES or not request.text.strip() or not request.origin_channel.strip():
        raise HTTPException(422, "INVALID_TEXT_INPUT")
    if len(request.text) > settings.processing_max_characters:
        raise HTTPException(422, "PROCESSING_TEXT_LIMIT")
    try:
        return DocumentService(DocumentRepository(session), get_storage(settings), settings.max_upload_bytes,
                               request.country).ingest_text(request.text, request.origin_channel.strip())
    except DocumentError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None
    except OSError:
        session.rollback()
        raise HTTPException(503, "UPLOAD_STORAGE_UNAVAILABLE") from None


@router.post("/documents/{document_id}/processing-jobs", response_model=JobResponse, status_code=202,
             dependencies=[Depends(require_permission("DOCUMENTS_PROCESS"))])
def create_job(document_id: UUID, session: Db):
    try:
        job = enqueue(session, document_id)
        session.commit()
        return job
    except DocumentError as exc:
        session.rollback()
        raise HTTPException(exc.status_code, exc.detail) from None


@router.get("/processing-jobs/{job_id}", response_model=JobResponse,
            dependencies=[Depends(require_permission("DOCUMENTS_READ"))])
def get_job(job_id: UUID, session: Db):
    job = session.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))
    if not job:
        raise HTTPException(404, "JOB_NOT_FOUND")
    return job


@router.get("/documents/{document_id}/processing-jobs/latest", response_model=JobResponse,
            dependencies=[Depends(require_permission("DOCUMENTS_READ"))])
def latest_job(document_id: UUID, session: Db):
    job = session.scalar(select(ProcessingJob).where(ProcessingJob.document_id == document_id)
                         .order_by(ProcessingJob.created_at.desc()).limit(1))
    if not job:
        raise HTTPException(404, "JOB_NOT_FOUND")
    return job


@router.get("/admin/document-policies", dependencies=[Depends(require_superadmin)])
def policies(session: Db):
    return [{"document_type": p.document_type, "version": p.version, **p.configuration}
            for p in session.scalars(select(DocumentPolicy).order_by(DocumentPolicy.document_type))]


@router.get("/document-policies/{kind}", dependencies=[Depends(require_permission("DOCUMENTS_READ"))])
def policy_for_review(kind: str, session: Db):
    row = session.get(DocumentPolicy, kind)
    if row is None:
        raise HTTPException(404, "POLICY_NOT_FOUND")
    return {"document_type": kind, "version": row.version, **row.configuration}


@router.put("/admin/document-policies/{kind}", dependencies=[Depends(require_superadmin)])
def save_policy(kind: str, request: PolicyInput, session: Db):
    row = session.scalar(select(DocumentPolicy).where(DocumentPolicy.document_type == kind).with_for_update())
    if row is None:
        raise HTTPException(404, "POLICY_NOT_FOUND")
    fields = next(t["fields"] for t in document_catalog()["types"] if t["code"] == kind)
    allowed = set(fields) | {n for g in REQUIRED_GROUPS.get(kind, ()) for n in g}
    if any(n not in allowed for g in request.required_groups for n in g):
        raise HTTPException(422, "UNKNOWN_REQUIRED_FIELD")
    if request.expected_version != row.version:
        raise HTTPException(409, "POLICY_VERSION_CONFLICT")
    row.configuration = request.model_dump(exclude={"expected_version"})
    row.version += 1
    row.updated_at = datetime.now(UTC)
    session.commit()
    return {"document_type": kind, "version": row.version, **row.configuration}


@router.get("/documents/{document_id}/backups", dependencies=[Depends(require_permission("DOCUMENTS_READ"))])
def backups(document_id: UUID, session: Db):
    if not DocumentRepository(session).get(document_id):
        raise HTTPException(404, "DOCUMENT_NOT_FOUND")
    return [{"id": r.id, "status": r.status, "attempts": r.attempts, "error_code": r.error_code, "created_at": r.created_at}
            for r in session.scalars(select(ResultBackup).where(ResultBackup.document_id == document_id).order_by(ResultBackup.id.desc()))]


@router.post("/documents/{document_id}/backups/retry", status_code=204,
             dependencies=[Depends(require_permission("DOCUMENTS_PROCESS"))])
def retry_backups(document_id: UUID, session: Db):
    for row in session.scalars(select(ResultBackup).where(ResultBackup.document_id == document_id,
                               ResultBackup.status == "FAILED").with_for_update()):
        row.status, row.retry_at = "PENDING", datetime.now(UTC)
    session.commit()
