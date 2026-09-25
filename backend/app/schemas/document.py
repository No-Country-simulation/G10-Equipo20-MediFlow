from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from app.schemas.lifecycle import DocumentStatus


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    original_filename: str
    format: Literal["pdf", "jpeg", "png"] | None
    size_bytes: int | None = Field(ge=0)
    received_at: datetime
    country: str = "EC"


class DocumentResponse(DocumentMetadata):
    status: DocumentStatus
    processing_attempts: int = 0
    rejection_reason: str | None = None


class DocumentList(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int
