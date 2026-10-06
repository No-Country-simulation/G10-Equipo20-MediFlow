"""Padrón de profesionales de la instalación (RN-A7, RN-CO5).

Quién puede firmar un documento clínico en esta clínica. Lo mantiene el administrador; la consulta en el
registro nacional (ReTHUS) es manual y se anota con fecha y quién la hizo. No contiene datos de pacientes.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class ProfesionalRegistrado(Base):
    __tablename__ = "profesionales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    registro: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # número de registro, sin prefijo ni puntos
    nombre: Mapped[str] = mapped_column(String(255))
    profesion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tipo_documento: Mapped[str | None] = mapped_column(String(8), nullable=True)
    numero_documento: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    registro_consultado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # consulta manual en ReTHUS
    registro_consultado_por: Mapped[str | None] = mapped_column(String(128), nullable=True)
    creado_por: Mapped[str] = mapped_column(String(128))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
