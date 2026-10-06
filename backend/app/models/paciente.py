"""Directorio de pacientes de la instalación (RN-M6, RN-N5).

Un paciente se identifica por país, tipo y número de documento. Cada documento clínico enrutado
se vincula a su paciente, así se puede localizar todo lo asociado a una persona.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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


class SolicitudTitular(Base):
    """RN-M6: el titular (o quien lo representa) pide que una persona revise una decisión automatizada sobre uno
    de sus documentos. Se registra con quién la presentó, por qué canal y el plazo legal del pack para responder;
    la respuesta queda firmada por la cuenta que revisó."""

    __tablename__ = "solicitudes_titular"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", name="fk_solicitudes_paciente"), index=True)
    documento_id: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    presentada_por: Mapped[str] = mapped_column(String(16))  # titular | representante
    canal: Mapped[str] = mapped_column(String(16))  # presencial | telefono | correo | escrito
    motivo: Mapped[str] = mapped_column(Text)
    registrada_por: Mapped[str] = mapped_column(String(128))
    registrada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    vence_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # plazo legal del pack (RN-CO19)
    estado: Mapped[str] = mapped_column(String(16), default="pendiente", index=True)  # pendiente | respondida
    resultado: Mapped[str | None] = mapped_column(String(16), nullable=True)  # mantenida | corregida
    respuesta: Mapped[str | None] = mapped_column(Text, nullable=True)
    respondida_por: Mapped[str | None] = mapped_column(String(128), nullable=True)
    respondida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
