"""Cola persistente de procesamiento (RN-P2, RN-P5). Cada documento recibido es un trabajo que un worker aparte
toma, arrienda por un rato y termina. Si el worker cae a mitad, el arriendo vence y otro lo retoma."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


_VIVO = "estado IN ('EN_COLA', 'EN_CURSO')"


class TrabajoProcesamiento(Base):
    __tablename__ = "trabajos_procesamiento"
    __table_args__ = (
        # Un documento tiene a lo sumo un trabajo vivo: dos workers nunca lo procesan a la vez.
        Index("ix_trabajo_vivo_por_documento", "documento_pk", unique=True, postgresql_where=text(_VIVO), sqlite_where=text(_VIVO)),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    documento_pk: Mapped[int] = mapped_column(ForeignKey("documentos.id"), index=True)
    documento_id: Mapped[str] = mapped_column(String(128))
    estado: Mapped[str] = mapped_column(String(16), default="EN_COLA")  # EN_COLA | EN_CURSO | TERMINADO | FALLIDO
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    proximo_intento_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)  # espera entre reintentos
    arrendado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # vencido: otro worker lo retoma
    token: Mapped[str | None] = mapped_column(String(36), nullable=True)  # identifica al worker que lo tiene
    intento: Mapped[int] = mapped_column(Integer, default=0)
    codigo_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    solicitado_por: Mapped[str | None] = mapped_column(String(128), nullable=True)
