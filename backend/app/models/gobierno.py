"""Gobierno de la instalación: versiones de configuración (RN-L4, RN-L5), usuarios (RN-K4, RN-K5)
y registro de accesos a documentos (RN-K3). Nada de esto contiene datos del paciente (RN-M4)."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class VersionConfiguracion(Base):
    """RN-L4: cada cambio es una versión nueva con autor, fecha y vigencia. Nunca se edita una versión."""

    __tablename__ = "versiones_configuracion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # se asigna al entrar en vigencia
    autor: Mapped[str] = mapped_column(String(128))
    motivo: Mapped[str] = mapped_column(Text)
    cambios_json: Mapped[dict] = mapped_column(JSON)  # {umbrales: {clave: valor}, ampliaciones: {...}}
    simulacion_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # RN-L6
    toca_seguridad: Mapped[bool] = mapped_column(Boolean, default=False)  # RN-L5
    aprobaciones_json: Mapped[list] = mapped_column(JSON, default=list)  # [{usuario, fecha_hora}]
    estado: Mapped[str] = mapped_column(String(16), default="propuesta", index=True)  # propuesta | vigente | reemplazada | rechazada
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    vigente_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vigente_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cierre_por: Mapped[str | None] = mapped_column(String(128), nullable=True)  # quien rechazó, si aplica
    cierre_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)


class Usuario(Base):
    """Tabla K: un usuario tiene un rol. RN-K4: desactivado pierde acceso; RN-K5: las cuentas de servicio no firman."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(256))
    rol: Mapped[str] = mapped_column(String(32))
    tipo: Mapped[str] = mapped_column(String(16), default="persona")  # persona | servicio
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_por: Mapped[str] = mapped_column(String(128))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    desactivado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AccesoDocumento(Base):
    """RN-K3: quién, cuándo y qué vio. Solo el ID del documento (RN-M4)."""

    __tablename__ = "accesos_documento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    documento_id: Mapped[str] = mapped_column(String(128), index=True)
    usuario: Mapped[str] = mapped_column(String(128), index=True)
    accion: Mapped[str] = mapped_column(String(32))  # detalle | original | vista_previa
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
