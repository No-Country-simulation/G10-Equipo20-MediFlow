from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from app.schemas.lifecycle import DocumentStatus


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
    method: Literal["embedded_text", "gemini_ocr", "human_corrected"]
    engine: Literal["pymupdf", "gemini"] | None = None
    uncertain: bool = False


class ContentResult(StructuredModel):
    pages: list[ContentPage]


class Evidence(StructuredModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1)


class ClassificationResult(StructuredModel):
    document_type: Literal[
        "ECHOCARDIOGRAM_REPORT", "SPIROMETRY_REPORT", "CHEST_IMAGING_REPORT",
        "ECG_REPORT", "OTHER", "UNKNOWN",
    ]
    specialty: Literal["CARDIOLOGY", "PULMONOLOGY", "CARDIOPULMONARY", "OTHER", "UNKNOWN"]
    evidence: Evidence | None
    reason: str


class ExtractedField(StructuredModel):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1)
    unit: str | None
    evidence: Evidence


class ExtractionResult(StructuredModel):
    fields: list[ExtractedField]


class ValidationResult(StructuredModel):
    valid: bool
    requires_human_review: bool
    issues: list[str]


class RoutingResult(StructuredModel):
    destination: Literal["CARDIOLOGIA", "NEUMOLOGIA", "CARDIOPULMONAR"]
    routed_at: datetime
    rule_version: str = "cardiopulmonary-v1"
    delivery_status: Literal["PENDING_INTEGRATION"] = "PENDING_INTEGRATION"


class ProcessingResult(StructuredModel):
    document_id: UUID
    status: DocumentStatus
    processed_at: datetime
    pipeline_version: str = "cardiopulmonary-v2"
    provider: str = "gemini"
    model: str
    content: ContentResult | None = None
    classification: ClassificationResult | None = None
    extraction: ExtractionResult | None = None
    validation: ValidationResult | None = None
    error_code: str | None = None
    routing: RoutingResult | None = None


class ReviewRequest(StructuredModel):
    action: Literal["APPROVE", "CORRECT"]
    reviewer: str = Field(min_length=1, max_length=100)
    notes: str = Field(min_length=1, max_length=2000)
    confirmed_source_review: Literal[True]
    content: ContentResult | None = None
    classification: ClassificationResult | None = None
    extraction: ExtractionResult | None = None


class ReviewAudit(StructuredModel):
    action: Literal["APPROVE", "CORRECT"]
    reviewer: str
    notes: str
    reviewed_at: datetime
    previous_result: ProcessingResult
