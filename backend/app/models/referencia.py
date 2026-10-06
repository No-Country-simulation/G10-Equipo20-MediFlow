"""Conjunto de referencia (RN-R2): cada corrección humana, seudonimizada.

Guarda lo que vio el LLM (texto con tokens y su propuesta con tokens), lo que la persona corrigió y la prioridad
antes y después. Sirve para medir un cambio de modelo, prompt o reglas antes de sacarlo (RN-R3). Nunca lleva
nombres ni documentos reales: lo identificante se reemplaza por su token (RN-M1, RN-M4).
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class CasoReferencia(Base):
    __tablename__ = "casos_referencia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    correccion_id: Mapped[int] = mapped_column(ForeignKey("correcciones.id", name="fk_referencia_correccion"), unique=True)
    documento_id: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    origen: Mapped[str] = mapped_column(String(16))  # correccion | transcripcion
    campo: Mapped[str] = mapped_column(String(256), index=True)
    extraido: Mapped[object | None] = mapped_column(JSON, nullable=True)  # seudonimizado
    corregido: Mapped[object | None] = mapped_column(JSON, nullable=True)  # seudonimizado
    usuario: Mapped[str] = mapped_column(String(128))
    tipo_documento: Mapped[str | None] = mapped_column(String(64), nullable=True)
    canal_origen: Mapped[str] = mapped_column(String(32))
    pais: Mapped[str] = mapped_column(String(2))
    texto_seudonimizado: Mapped[str | None] = mapped_column(Text, nullable=True)  # lo que vio el LLM (RN-M1)
    propuesta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # la propuesta del LLM, con tokens
    nivel_propuesto: Mapped[str | None] = mapped_column(String(16), nullable=True)  # lo que propuso el LLM
    nivel_antes: Mapped[str | None] = mapped_column(String(16), nullable=True)  # lo que decidieron las reglas antes de la corrección
    nivel_resultante: Mapped[str | None] = mapped_column(String(16), nullable=True)  # tras la corrección
    hallazgos_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    modelo_llm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version_prompt: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version_reglas: Mapped[str | None] = mapped_column(String(16), nullable=True)
    version_pack: Mapped[str | None] = mapped_column(String(16), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
