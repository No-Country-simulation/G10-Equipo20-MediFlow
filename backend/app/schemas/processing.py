from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from app.schemas.lifecycle import DocumentStatus
from app.core.document_catalog import DocumentType, Specialty


class StructuredModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OCRPage(StructuredModel):
    page: int = Field(ge=1)
    text: str
    uncertain: bool


class OCRResult(StructuredModel):
    pages: list[OCRPage]


class ContentPage(StructuredModel):
    page: int = Field(ge=1)
    text: str
    method: Literal["embedded_text", "gemini_ocr", "openai_ocr", "human_corrected"]
    engine: Literal["pymupdf", "gemini", "openai"] | None = None
    uncertain: bool = False


class ContentResult(StructuredModel):
    pages: list[ContentPage]


class Evidence(StructuredModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1)


class ClassificationResult(StructuredModel):
    document_type: DocumentType
    specialty: Specialty
    evidence: Evidence | None
    reason: str


class ExtractedField(StructuredModel):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1)
    unit: str | None
    evidence: Evidence
    # Optional grouping for multiple medications/tests; old results remain readable.
    entity_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{0,59}$")


class ExtractionResult(StructuredModel):
    fields: list[ExtractedField]


class ValidationResult(StructuredModel):
    valid: bool
    requires_human_review: bool
    issues: list[str]
    rule_version: str = "documentary-v1"


class PriorityResult(StructuredModel):
    level: Literal["ROUTINE", "URGENT", "CRITICAL"]
    source: Literal["DEFAULT", "EXPLICIT"]
    evidence: Evidence | None = None
    ambiguous: bool = False
    rule_version: str = "explicit-priority-v1"


class QualityComponents(StructuredModel):
    readability: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    evidence: float = Field(ge=0, le=1)
    consistency: float = Field(ge=0, le=1)


class QualityResult(StructuredModel):
    score: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)
    components: QualityComponents
    rule_version: str = "document-quality-v1"


class LocalAlert(StructuredModel):
    level: Literal["URGENT", "CRITICAL"]
    message: str
    evidence: Evidence
    status: Literal["REGISTERED_LOCAL"] = "REGISTERED_LOCAL"


class RoutingResult(StructuredModel):
    destination: str
    routed_at: datetime
    rule_version: str = "cardiopulmonary-v1"
    delivery_status: Literal["PENDING_INTEGRATION", "DELIVERED_LOCAL"] = "PENDING_INTEGRATION"
    external_delivery_status: Literal["PENDING_INTEGRATION"] = "PENDING_INTEGRATION"


class PatientMatch(StructuredModel):
    status: Literal["NOT_FOUND", "INVALID_FORMAT", "REVIEW_REQUIRED", "VALID_CANDIDATE", "CREATED", "LINKED"]
    identity_type: str | None = None
    identity_number: str | None = None
    patient_id: int | None = None
    reason: str | None = None


class ProcessingResult(StructuredModel):
    document_id: UUID
    status: DocumentStatus
    processed_at: datetime
    pipeline_version: str = "cardiopulmonary-v3"
    provider: str = "gemini"
    model: str
    content: ContentResult | None = None
    classification: ClassificationResult | None = None
    extraction: ExtractionResult | None = None
    validation: ValidationResult | None = None
    priority: PriorityResult | None = None
    quality: QualityResult | None = None
    local_alert: LocalAlert | None = None
    error_code: str | None = None
    routing: RoutingResult | None = None
    patient: PatientMatch | None = None


class ReviewRequest(StructuredModel):
    action: Literal["APPROVE", "CORRECT", "REJECT"]
    reviewer: str = Field(min_length=1, max_length=100)
    notes: str = Field(min_length=1, max_length=2000)
    confirmed_source_review: Literal[True]
    content: ContentResult | None = None
    classification: ClassificationResult | None = None
    extraction: ExtractionResult | None = None


class ReviewAudit(StructuredModel):
    action: Literal["APPROVE", "CORRECT", "REJECT"]
    reviewer: str
    notes: str
    reviewed_at: datetime
    previous_result: ProcessingResult
