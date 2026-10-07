from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.document import Base


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (Index("ix_processing_jobs_active_document", "document_id", unique=True,
                           postgresql_where=text("status IN ('QUEUED','RUNNING')")),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.document_id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token: Mapped[UUID | None] = mapped_column(Uuid)
    active_node: Mapped[str | None] = mapped_column(String(50))
    completed_nodes: Mapped[list] = mapped_column(JSONB, default=list)
    provider_calls: Mapped[dict] = mapped_column(JSONB, default=dict)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    policy_snapshot: Mapped[dict | None] = mapped_column(JSONB)


class DocumentPolicy(Base):
    __tablename__ = "document_policies"
    document_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    configuration: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResultBackup(Base):
    __tablename__ = "result_backups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.document_id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
