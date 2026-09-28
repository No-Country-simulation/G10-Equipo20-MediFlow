"""Conservative document-to-patient matching; format is not proof of identity."""

import re
import unicodedata
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.patient import Patient
from app.schemas.processing import ExtractionResult, PatientMatch, ValidationResult
from app.services.errors import DocumentError


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def validate_identity(country: str, raw: str) -> tuple[str, str] | None:
    value = re.sub(r"[.\s\-]", "", raw).upper()
    patterns = {
        "AR": ("DNI", r"\d{7,8}"), "BO": ("CI", r"\d{5,8}(?:[A-Z0-9]{1,2})?"),
        "BR": ("CPF", r"\d{11}"), "CL": ("RUN", r"\d{7,8}[0-9K]"),
        "CO": ("CC", r"\d{6,10}"), "EC": ("CEDULA", r"\d{10}"),
        "PY": ("CI", r"\d{1,9}"), "PE": ("DNI", r"\d{8}"),
        "UY": ("CI", r"\d{7,8}"), "VE": ("CI", r"[VE]\d{6,8}"),
        "MX": ("CURP", r"[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d"),
    }
    if country == "AR" and re.fullmatch(r"\d{11}", value):
        return "CUIL", value
    identity_type, pattern = patterns.get(country, ("", r"(?!)"))
    if re.fullmatch(pattern, value):
        return identity_type, value
    return None


def patient_fields(extraction: ExtractionResult | None) -> tuple[list[str], list[str], int | None]:
    fields = extraction.fields if extraction else []
    identities = [field.value for field in fields if field.name == "patient_identity"]
    names = [field.value for field in fields if field.name == "patient_name"]
    ages = [int(field.value) for field in fields if field.name == "patient_age"
            and field.value.isdecimal() and 0 <= int(field.value) <= 130]
    return identities, names, ages[0] if ages else None


def assess_patient(extraction: ExtractionResult | None, country: str,
                   validation: ValidationResult, session: Session | None) -> PatientMatch:
    identities, names, _ = patient_fields(extraction)
    if not identities:
        return PatientMatch(status="NOT_FOUND", reason="PATIENT_IDENTITY_NOT_FOUND")
    if len(identities) != 1 or len(names) > 1:
        validation.valid = False
        validation.requires_human_review = True
        validation.issues.append("PATIENT_IDENTITY_AMBIGUOUS")
        return PatientMatch(status="REVIEW_REQUIRED", reason="PATIENT_IDENTITY_AMBIGUOUS")
    normalized = validate_identity(country, identities[0])
    if normalized is None:
        return PatientMatch(status="INVALID_FORMAT", reason="PATIENT_IDENTITY_INVALID_FORMAT")
    identity_type, number = normalized
    if not names or not names[0].strip():
        validation.valid = False
        validation.requires_human_review = True
        validation.issues.append("PATIENT_NAME_MISSING")
        return PatientMatch(status="REVIEW_REQUIRED", identity_type=identity_type,
                            identity_number=number, reason="PATIENT_NAME_MISSING")
    if session is not None:
        existing = session.scalar(select(Patient).where(Patient.country == country,
                            Patient.identity_type == identity_type, Patient.identity_number == number))
        if existing and normalize_name(existing.name) != normalize_name(names[0]):
            validation.valid = False
            validation.requires_human_review = True
            validation.issues.append("PATIENT_IDENTITY_CONFLICT")
            return PatientMatch(status="REVIEW_REQUIRED", identity_type=identity_type,
                                identity_number=number, reason="PATIENT_IDENTITY_CONFLICT")
    return PatientMatch(status="VALID_CANDIDATE", identity_type=identity_type,
                        identity_number=number)


def link_patient(document: Document, extraction: ExtractionResult | None,
                 match: PatientMatch, session: Session) -> PatientMatch:
    if match.status != "VALID_CANDIDATE":
        document.patient_id = None
        document.patient_match_status = match.status
        document.patient_match_reason = match.reason
        return match
    _, names, age = patient_fields(extraction)
    patient = session.scalar(select(Patient).where(Patient.country == document.country,
                            Patient.identity_type == match.identity_type,
                            Patient.identity_number == match.identity_number).with_for_update())
    if patient and normalize_name(patient.name) != normalize_name(names[0]):
        raise DocumentError(409, "PATIENT_IDENTITY_CONFLICT")
    status = "LINKED"
    if patient is None:
        now = datetime.now(UTC)
        patient = Patient(country=document.country, identity_type=match.identity_type,
                          identity_number=match.identity_number, name=names[0].strip(), age=age,
                          created_at=now, updated_at=now, audit_history=[])
        session.add(patient)
        session.flush()
        status = "CREATED"
    document.patient_id = patient.id
    document.patient_match_status = status
    document.patient_match_reason = None
    return match.model_copy(update={"status": status, "patient_id": patient.id})
