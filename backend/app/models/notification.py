from datetime import datetime
from uuid import UUID
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.document import Base


class SlackNotification(Base):
    __tablename__ = 'slack_notifications'
    __table_args__ = (UniqueConstraint('document_id', 'level', name='uq_slack_document_level'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('documents.document_id', ondelete='CASCADE'), index=True)
    level: Mapped[str] = mapped_column(String(10))
    destination_code: Mapped[str | None] = mapped_column(String(60), ForeignKey('destinations.code', ondelete='RESTRICT'))
    status: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retryable: Mapped[bool] = mapped_column(Boolean, default=True)
    retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
