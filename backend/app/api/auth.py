from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import (COOKIE_NAME, create_session, current_account, password_hash,
                           password_matches, require_patient, same_origin, token_hash)
from app.core.countries import COUNTRY_CODES
from app.core.database import get_session
from app.core.config import Settings, get_settings
from app.models.account import Account, LoginSession
from app.models.document import Document
from app.models.patient import Patient
from app.schemas.document import DocumentResponse
from app.services.patients import validate_identity
from app.services.storage import get_storage
from app.services.errors import DocumentError
from uuid import UUID

router = APIRouter(prefix="/auth", tags=["authentication"])
Db = Annotated[Session, Depends(get_session)]


class RegisterInput(BaseModel):
    country: str
    identity_number: str = Field(min_length=1, max_length=40)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginInput(BaseModel):
    country: str | None = None
    identity_number: str | None = None
    email: EmailStr | None = None
    password: str


def public_account(account: Account, session: Session) -> dict:
    from app.core.permissions import effective_permissions
    permissions, denials = effective_permissions(account, session)
    return {"id": account.id, "role": account.role, "country": account.country,
            "identity_number": account.identity_number, "email": account.email,
            "name": account.name, "permissions": permissions, "denied_permissions": denials}


@router.post("/register", status_code=201, dependencies=[Depends(same_origin)])
def register(payload: RegisterInput, session: Db):
    if payload.country not in COUNTRY_CODES:
        raise HTTPException(422, "UNSUPPORTED_COUNTRY")
    identity = validate_identity(payload.country, payload.identity_number)
    if identity is None:
        raise HTTPException(422, "PATIENT_IDENTITY_INVALID_FORMAT")
    account = Account(email=str(payload.email).lower(), password_hash=password_hash(payload.password),
                      role="PATIENT", country=payload.country, identity_type=identity[0],
                      identity_number=identity[1], created_at=datetime.now(UTC))
    session.add(account)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "ACCOUNT_ALREADY_EXISTS") from None
    return {"message": "ACCOUNT_CREATED"}


@router.post("/patient-login", dependencies=[Depends(same_origin)])
def patient_login(payload: LoginInput, request: Request, response: Response, session: Db):
    identity = validate_identity(payload.country or "", payload.identity_number or "")
    if identity is None:
        raise HTTPException(401, "INVALID_CREDENTIALS")
    account = session.scalar(select(Account).where(Account.role == "PATIENT",
        Account.country == payload.country, Account.identity_type == identity[0],
        Account.identity_number == identity[1]))
    if account is None or not account.active or not password_matches(payload.password, account.password_hash):
        raise HTTPException(401, "INVALID_CREDENTIALS")
    create_session(account, session, response, request)
    return public_account(account, session)


@router.post("/admin-login", dependencies=[Depends(same_origin)])
def admin_login(payload: LoginInput, request: Request, response: Response, session: Db):
    account = session.scalar(select(Account).where(Account.email == str(payload.email or "").lower(),
                                                   Account.role.in_(("SUPERADMIN", "EMPLOYEE"))))
    if account is None or not account.active or not password_matches(payload.password, account.password_hash):
        raise HTTPException(401, "INVALID_CREDENTIALS")
    create_session(account, session, response, request)
    return public_account(account, session)


@router.get("/me")
def me(account: Annotated[Account, Depends(current_account)], session: Db):
    return public_account(account, session)


@router.post("/logout", dependencies=[Depends(same_origin)])
def logout(request: Request, response: Response, session: Db):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        record = session.get(LoginSession, token_hash(token))
        if record is not None:
            session.delete(record)
            session.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"message": "SIGNED_OUT"}


@router.get("/my-documents", response_model=list[DocumentResponse])
def my_documents(account: Annotated[Account, Depends(require_patient)], session: Db):
    patient = session.scalar(select(Patient).where(Patient.country == account.country,
        Patient.identity_type == account.identity_type, Patient.identity_number == account.identity_number))
    if patient is None:
        return []
    return [DocumentResponse.model_validate(item) for item in session.scalars(
        select(Document).where(Document.patient_id == patient.id).order_by(Document.received_at.desc()))]


@router.get("/my-documents/{document_id}/file")
def my_document_file(document_id: UUID, account: Annotated[Account, Depends(require_patient)],
                     session: Db, settings: Annotated[Settings, Depends(get_settings)]):
    document = session.get(Document, document_id)
    if document is None or document.patient_id is None:
        raise HTTPException(404, "DOCUMENT_NOT_FOUND")
    patient = session.get(Patient, document.patient_id)
    if patient is None or (patient.country, patient.identity_type, patient.identity_number) != (
            account.country, account.identity_type, account.identity_number):
        raise HTTPException(404, "DOCUMENT_NOT_FOUND")
    if not document.storage_key:
        raise HTTPException(404, "DOCUMENT_FILE_NOT_FOUND")
    try:
        with get_storage(settings, document.storage_backend, document.storage_bucket).materialize(
                document.storage_key, settings.max_upload_bytes) as path:
            data = path.read_bytes()
    except (DocumentError, OSError):
        raise HTTPException(503, "DOCUMENT_STORAGE_UNAVAILABLE") from None
    return Response(data, media_type={"pdf": "application/pdf", "jpeg": "image/jpeg", "png": "image/png", "text": "application/json"}[document.format],
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
