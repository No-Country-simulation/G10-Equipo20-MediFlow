from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_documents_size_positive"),
        CheckConstraint("format IN ('pdf', 'jpeg', 'png')", name="ck_documents_format"),
        CheckConstraint("status IN ('RECIBIDO', 'VALIDADO', 'CLASIFICADO', 'EXTRAIDO', 'EVALUADO', 'ENRUTADO', 'ENTREGADO', 'RECHAZADO', 'FALLO_TECNICO', 'EN_REVISION_HUMANA', 'RESUELTO')", name="ck_documents_status"),
    )

    document_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    format: Mapped[str | None] = mapped_column(String(4))
    size_bytes: Mapped[int | None]
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    storage_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    processing_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    processing_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    rejection_reason: Mapped[str | None] = mapped_column(String(255))
    state_history: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    review_history: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    storage_backend: Mapped[str] = mapped_column(String(10), default="local", server_default="local")
    storage_bucket: Mapped[str | None] = mapped_column(String(63))
    country: Mapped[str] = mapped_column(String(2), default="EC", server_default="EC")
