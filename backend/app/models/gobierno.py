"""Gobierno de la instalación: versiones de configuración (RN-L4, RN-L5), usuarios (RN-K4, RN-K5)
y registro de accesos a documentos (RN-K3). Nada de esto contiene datos del paciente (RN-M4)."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
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


class Rol(Base):
    """Tabla K como datos: qué ve y qué puede cada rol. Se siembra desde app/services/roles_base.py."""

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    orden: Mapped[int] = mapped_column(Integer)
    nombre: Mapped[str] = mapped_column(String(64))
    descripcion: Mapped[str] = mapped_column(Text)
    ve: Mapped[str] = mapped_column(String(128))  # columna "Ve" de la tabla K
    puede: Mapped[str] = mapped_column(String(128))  # columna "Puede" de la tabla K
    secciones: Mapped[list] = mapped_column(JSON)  # lo que el frontend muestra en el menú (RN-K1)
    acciones: Mapped[list] = mapped_column(JSON)  # lo que la API deja firmar (RN-K1, RN-K2)
    tipos_documento: Mapped[list] = mapped_column(JSON)  # RN-J9: vacío = todos
    ve_documentos: Mapped[bool] = mapped_column(Boolean)
    ruta_inicial: Mapped[str] = mapped_column(String(64))
    modo_discreto: Mapped[bool] = mapped_column(Boolean)
    alto_contraste: Mapped[bool] = mapped_column(Boolean)
    pantalla_compartida: Mapped[bool] = mapped_column(Boolean)

    def como_dict(self) -> dict:
        return {
            "id": self.id, "nombre": self.nombre, "descripcion": self.descripcion, "ve": self.ve, "puede": self.puede,
            "secciones": list(self.secciones), "acciones": list(self.acciones), "tipos_documento": list(self.tipos_documento),
            "ve_documentos": self.ve_documentos, "ruta_inicial": self.ruta_inicial, "modo_discreto": self.modo_discreto,
            "alto_contraste": self.alto_contraste, "pantalla_compartida": self.pantalla_compartida,
        }


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
    # Hash PBKDF2 de la clave. Sin clave la cuenta no inicia sesión; con clave nadie firma en su nombre sin sesión (RN-K5).
    clave_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ultimo_ingreso_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SesionUsuario(Base):
    """Sesión abierta de una cuenta. Solo se guarda el hash del token de la cookie."""

    __tablename__ = "sesiones"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", name="fk_sesiones_usuario", ondelete="CASCADE"), index=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class AccesoDocumento(Base):
    """RN-K3: quién, cuándo y qué vio. Solo el ID del documento (RN-M4)."""

    __tablename__ = "accesos_documento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    documento_id: Mapped[str] = mapped_column(String(128), index=True)
    usuario: Mapped[str] = mapped_column(String(128), index=True)
    accion: Mapped[str] = mapped_column(String(32))  # detalle | original | vista_previa
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
