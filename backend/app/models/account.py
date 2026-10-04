from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.document import Base
from app.models.administration import Role  # Registers the FK target for standalone bootstrap commands.


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
    name: Mapped[str | None] = mapped_column(String(255))
    contact: Mapped[str | None] = mapped_column(String(100))
    assigned_role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class LoginSession(Base):
    __tablename__ = "login_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
