"""Alertas críticas con acuse (RN-F1, RN-J7, RN-Q1, RN-Q5) y correcciones humanas (RN-J8)."""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Alerta(Base):
    """RN-Q1: una alerta por documento, versión y nivel."""

    __tablename__ = "alertas"
    __table_args__ = (UniqueConstraint("documento_pk", "nivel", name="uq_alerta_documento_nivel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    documento_pk: Mapped[int] = mapped_column(ForeignKey("documentos.id"), index=True)
    documento_id: Mapped[str] = mapped_column(String(128), index=True)
    nivel: Mapped[str] = mapped_column(String(16))
    canal: Mapped[str] = mapped_column(String(16))
    destinatario: Mapped[str] = mapped_column(String(128))
    mensaje: Mapped[str] = mapped_column(String(512))  # RN-Q4: sin datos del paciente
    enlace: Mapped[str | None] = mapped_column(String(512), nullable=True)
    estado_acuse: Mapped[str] = mapped_column(String(16), default="pendiente")
    emitida_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    acusado_por: Mapped[str | None] = mapped_column(String(128), nullable=True)  # RN-Q5
    acusado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalamientos: Mapped[list | None] = mapped_column(JSON, nullable=True)  # RN-F2

    documento = relationship("Documento", back_populates="alertas")


class Correccion(Base):
    """RN-J8: cada corrección se guarda como par extraído-corregido por campo."""

    __tablename__ = "correcciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    documento_pk: Mapped[int] = mapped_column(ForeignKey("documentos.id"), index=True)
    campo: Mapped[str] = mapped_column(String(256))
    extraido: Mapped[object | None] = mapped_column(JSON, nullable=True)
    corregido: Mapped[object | None] = mapped_column(JSON, nullable=True)
    usuario: Mapped[str] = mapped_column(String(128))
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    documento = relationship("Documento", back_populates="correcciones")
