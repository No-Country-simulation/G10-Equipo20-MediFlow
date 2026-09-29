from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Identity, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.document import Base


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("country", "identity_type", "identity_number", name="uq_account_identity"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    country: Mapped[str | None] = mapped_column(String(2))
    identity_type: Mapped[str | None] = mapped_column(String(16))
    identity_number: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LoginSession(Base):
    __tablename__ = "login_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
