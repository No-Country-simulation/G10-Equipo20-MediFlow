from datetime import datetime

from sqlalchemy import DateTime, Identity, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.document import Base


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("country", "identity_type", "identity_number", name="uq_patient_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    identity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    identity_number: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    age: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    audit_history: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
