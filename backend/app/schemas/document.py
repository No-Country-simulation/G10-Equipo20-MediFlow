from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    original_filename: str
    format: Literal["pdf", "jpeg", "png"]
    size_bytes: int = Field(gt=0)
    received_at: datetime


class DocumentResponse(DocumentMetadata):
    status: Literal["UPLOADED"]
