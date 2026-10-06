"""Persistencia del documento y de su historial de estados (RN-I3, RN-G2, RN-O2)."""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Documento(Base):
    __tablename__ = "documentos"
    __table_args__ = (UniqueConstraint("documento_id", "version", name="uq_documento_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    documento_id: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # RN-O2
    hash_contenido: Mapped[str] = mapped_column(String(64), index=True)
    estado: Mapped[str] = mapped_column(String(32))
    canal_origen: Mapped[str] = mapped_column(String(32))
    pais_origen: Mapped[str] = mapped_column(String(2))
    tipo_contenido: Mapped[str] = mapped_column(String(16))
    nombre_archivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    formato: Mapped[str | None] = mapped_column(String(16), nullable=True)  # txt | pdf | png | jpeg | desconocido (validado por contenido)
    num_paginas: Mapped[int] = mapped_column(Integer, default=1)
    paginas_json: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{pagina, tipo: texto|imagen, ruta?}]
    cobertura_paciente: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tamano_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status_backup: Mapped[str] = mapped_column(String(16), default="pendiente")  # RN-G3
    ruta_storage: Mapped[str | None] = mapped_column(String(512), nullable=True)  # RN-G1
    posible_duplicado_de: Mapped[str | None] = mapped_column(String(128), nullable=True)  # RN-O3
    codigo_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resultado_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # RN-G2
    # RN-M1: lo único que viaja a OpenAI es texto_seudonimizado. El mapa nunca sale de la instalación.
    texto_seudonimizado: Mapped[str | None] = mapped_column(Text, nullable=True)
    mapa_reidentificacion: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Propuesta del LLM ya re-identificada: base para re-ejecutar reglas tras una corrección (RN-J4).
    propuesta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    nivel_prioridad: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    tipo: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # RN-J9: cada rol lista solo sus tipos
    entregas_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # destino -> confirmado
    verificaciones_json: Mapped[list | None] = mapped_column(JSON, nullable=True)  # RN-J6: [{orden, usuario, fecha_hora}]
    autorizacion_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # RN-E5/RN-E9: {estado, usuario, motivo, fecha_hora}
    # RN-R5, RN-T3: modelo, versión del prompt y costo en tokens por documento.
    modelo_llm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version_prompt: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0)
    tokens_salida: Mapped[int] = mapped_column(Integer, default=0)
    # RN-M6: paciente del directorio al que pertenece el documento. Vacío hasta que se enruta con identidad válida (RN-N5).
    paciente_id: Mapped[int | None] = mapped_column(ForeignKey("pacientes.id", name="fk_documentos_paciente"), nullable=True, index=True)
    # RN-J3: revisor que tiene el caso. RN-J2/RN-J3: rol al que se escaló la revisión. Nada de esto cambia el estado.
    asignado_a: Mapped[str | None] = mapped_column(String(128), nullable=True)
    escalado_a_rol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    transiciones: Mapped[list["TransicionEstado"]] = relationship(
        back_populates="documento", cascade="all, delete-orphan", order_by="TransicionEstado.id"
    )
    alertas = relationship("Alerta", back_populates="documento", cascade="all, delete-orphan", order_by="Alerta.id")
    correcciones = relationship("Correccion", back_populates="documento", cascade="all, delete-orphan", order_by="Correccion.id")


class TransicionEstado(Base):
    """RN-I3: cada transición registra fecha y hora, actor (sistema o usuario) y motivo."""

    __tablename__ = "transiciones_estado"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    documento_pk: Mapped[int] = mapped_column(ForeignKey("documentos.id"), index=True)
    de_estado: Mapped[str | None] = mapped_column(String(32), nullable=True)
    a_estado: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(128))
    motivo: Mapped[str] = mapped_column(String(512))
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    documento: Mapped[Documento] = relationship(back_populates="transiciones")
