"""Directorio de pacientes de la instalación (RN-M6, RN-N5).

Un paciente se identifica por país, tipo y número de documento. Cada documento clínico enrutado
se vincula a su paciente, así se puede localizar todo lo asociado a una persona.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Paciente(Base):
    __tablename__ = "pacientes"
    __table_args__ = (UniqueConstraint("pais", "tipo_documento", "numero_documento", name="uq_paciente_identidad"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais: Mapped[str] = mapped_column(String(2))
    tipo_documento: Mapped[str] = mapped_column(String(16))
    numero_documento: Mapped[str] = mapped_column(String(32), index=True)
    nombre: Mapped[str] = mapped_column(String(255))
    edad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sexo: Mapped[str | None] = mapped_column(String(16), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    # RN-G4: cada edición humana queda con usuario, fecha, motivo y los valores anterior y nuevo.
    historial_json: Mapped[list] = mapped_column(JSON, default=list)
