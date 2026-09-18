from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_documents_size_positive"),
        CheckConstraint("format IN ('pdf', 'jpeg', 'png')", name="ck_documents_format"),
        CheckConstraint("status = 'UPLOADED'", name="ck_documents_status"),
    )

    document_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(4))
    size_bytes: Mapped[int]
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
