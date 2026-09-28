"""Country-scoped patient directory. Local superadministrator edits are audited."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import require_superadmin
from app.core.countries import COUNTRY_CODES
from app.core.database import get_session
from app.models.document import Document
from app.models.patient import Patient
from app.schemas.document import DocumentResponse
from app.services.patients import validate_identity

router = APIRouter(prefix="/patients", tags=["patients"])
Db = Annotated[Session, Depends(get_session)]
Admin = Annotated[dict[str, str], Depends(require_superadmin)]


class PatientOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    country: str
    identity_type: str
    identity_number: str
    name: str
    age: int | None
    created_at: datetime
    updated_at: datetime
    document_count: int = 0


class PatientList(BaseModel):
    items: list[PatientOutput]
    total: int
    limit: int
    offset: int


class PatientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    age: int | None = Field(default=None, ge=0, le=130)
    identity_number: str | None = Field(default=None, min_length=1, max_length=40)


def output(patient: Patient, session: Session) -> PatientOutput:
    count = session.scalar(select(func.count()).select_from(Document).where(Document.patient_id == patient.id)) or 0
    return PatientOutput.model_validate(patient).model_copy(update={"document_count": count})


@router.get("", response_model=PatientList)
def list_patients(session: Db, country: Annotated[str, Query(min_length=2, max_length=2)],
                  q: Annotated[str, Query(max_length=255)] = "",
                  limit: Annotated[int, Query(ge=1, le=100)] = 20,
                  offset: Annotated[int, Query(ge=0)] = 0):
    if country not in COUNTRY_CODES:
        raise HTTPException(422, "UNSUPPORTED_COUNTRY")
    query = select(Patient).where(Patient.country == country)
    if q.strip():
        term = q.strip()
        query = query.where(Patient.name.icontains(term, autoescape=True)
                            | Patient.identity_number.icontains(term, autoescape=True))
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    patients = session.scalars(query.order_by(Patient.id.desc()).limit(limit).offset(offset)).all()
    return PatientList(items=[output(patient, session) for patient in patients],
                       total=total, limit=limit, offset=offset)


@router.get("/{patient_id}", response_model=PatientOutput)
def get_patient(patient_id: int, session: Db):
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(404, "PATIENT_NOT_FOUND")
    return output(patient, session)


@router.get("/{patient_id}/documents", response_model=list[DocumentResponse])
def patient_documents(patient_id: int, session: Db):
    if session.get(Patient, patient_id) is None:
        raise HTTPException(404, "PATIENT_NOT_FOUND")
    return [DocumentResponse.model_validate(row) for row in session.scalars(
        select(Document).where(Document.patient_id == patient_id).order_by(Document.received_at.desc()))]


@router.patch("/{patient_id}", response_model=PatientOutput)
def update_patient(patient_id: int, payload: PatientUpdate, session: Db, admin: Admin):
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(404, "PATIENT_NOT_FOUND")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return output(patient, session)
    before = {field: getattr(patient, field) for field in ("name", "age", "identity_type", "identity_number")}
    if "name" in changes:
        patient.name = changes["name"].strip()
        if not patient.name:
            raise HTTPException(422, "PATIENT_NAME_REQUIRED")
    if "age" in changes:
        patient.age = changes["age"]
    if "identity_number" in changes:
        validated = validate_identity(patient.country, changes["identity_number"])
        if validated is None:
            raise HTTPException(422, "PATIENT_IDENTITY_INVALID_FORMAT")
        patient.identity_type, patient.identity_number = validated
    after = {field: getattr(patient, field) for field in before}
    # The audit event records the supplied changes and actor without logging clinical data.
    patient.updated_at = datetime.now(UTC)
    patient.audit_history = [*(patient.audit_history or []), {
        "at": patient.updated_at.isoformat(), "actor": admin["id"],
        "changed_fields": sorted(changes), "previous": before, "current": after,
    }]
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "PATIENT_IDENTITY_EXISTS") from None
    return output(patient, session)
