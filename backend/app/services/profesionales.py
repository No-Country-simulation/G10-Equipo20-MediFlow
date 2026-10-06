"""Verificación del profesional (RN-A7) contra el padrón de la instalación.

El registro nacional (ReTHUS) no expone una API confirmada: la consulta es una página web. Por eso la verificación
automática se hace contra el padrón que mantiene el administrador, y la consulta en ReTHUS queda anotada a mano,
con fecha y quién la hizo. El revisor siempre tiene el enlace del pack para consultar. Donde el pack declara que
no hay verificación en línea, el resultado es no_aplica y no penaliza el score.
"""
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.profesional import ProfesionalRegistrado
from app.packs.modelos import PackPais
from app.schemas.resultado import Profesional, VerificacionProfesional
from app.services.errores import ErrorDeRevision
from app.services.pacientes import nombres_compatibles

FUENTE = "padrón de profesionales de la instalación"


def normalizar_registro(valor: str | None) -> str:
    """"RM 45.678" y "45678" son el mismo registro: solo cuentan los caracteres alfanuméricos, sin el prefijo del tipo."""
    limpio = re.sub(r"[^0-9A-Za-z]", "", valor or "").upper()
    return re.sub(r"^(RM|TP|RP)(?=\d)", "", limpio)


def _solo_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


class ServicioProfesionales:
    def __init__(self, session: Session, pack: PackPais | None = None):
        self.session = session
        self.pack = pack

    # --- padrón (administración) ----------------------------------------------------------------

    def listar(self) -> list[ProfesionalRegistrado]:
        return list(self.session.scalars(select(ProfesionalRegistrado).order_by(ProfesionalRegistrado.nombre)))

    def obtener(self, profesional_id: int) -> ProfesionalRegistrado:
        p = self.session.get(ProfesionalRegistrado, profesional_id)
        if p is None:
            raise ErrorDeRevision(404, "profesional no encontrado")
        return p

    def crear(self, *, registro: str, nombre: str, actor: str, profesion: str | None = None, tipo_documento: str | None = None,
              numero_documento: str | None = None) -> ProfesionalRegistrado:
        registro = normalizar_registro(registro)
        if not registro:
            raise ErrorDeRevision(422, "el registro profesional es obligatorio")
        if not nombre.strip():
            raise ErrorDeRevision(422, "el nombre del profesional es obligatorio")
        if self.por_registro(registro) is not None:
            raise ErrorDeRevision(409, f"el registro {registro} ya está en el padrón")
        p = ProfesionalRegistrado(
            registro=registro, nombre=nombre.strip(), profesion=(profesion or "").strip() or None,
            tipo_documento=(tipo_documento or "").strip().upper() or None, numero_documento=_solo_digitos(numero_documento) or None,
            creado_por=actor.strip(),
        )
        self.session.add(p)
        self.session.commit()
        self.session.refresh(p)
        return p

    def cambiar_estado(self, profesional_id: int, *, activo: bool) -> ProfesionalRegistrado:
        p = self.obtener(profesional_id)
        p.activo = activo
        self.session.commit()
        self.session.refresh(p)
        return p

    def anotar_consulta_en_registro(self, profesional_id: int, *, usuario: str) -> ProfesionalRegistrado:
        """Quien consultó el registro nacional lo deja anotado: fecha y cuenta. No es una verificación automática."""
        p = self.obtener(profesional_id)
        p.registro_consultado_en = datetime.now(timezone.utc)
        p.registro_consultado_por = usuario.strip()
        self.session.commit()
        self.session.refresh(p)
        return p

    def por_registro(self, registro: str) -> ProfesionalRegistrado | None:
        return self.session.scalars(select(ProfesionalRegistrado).where(ProfesionalRegistrado.registro == normalizar_registro(registro))).first()

    def por_documento(self, numero_documento: str) -> ProfesionalRegistrado | None:
        digitos = _solo_digitos(numero_documento)
        if not digitos:
            return None
        return self.session.scalars(select(ProfesionalRegistrado).where(ProfesionalRegistrado.numero_documento == digitos)).first()

    # --- verificación (RN-A7) ---------------------------------------------------------------------

    def verificar(self, profesional: Profesional) -> VerificacionProfesional:
        if self.pack is None:
            raise ValueError("verificar exige el pack de la instalación")
        en_linea = self.pack.identidad_profesional.verificacion_en_linea
        if not en_linea.disponible:
            return VerificacionProfesional(estado="no_aplica", detalle=f"{self.pack.identidad_profesional.registro}: sin verificación en línea en el pack")
        enlace = en_linea.url
        if not (normalizar_registro(profesional.registro_profesional) or _solo_digitos(profesional.numero_documento)):
            return VerificacionProfesional(estado="sin_datos", fuente=FUENTE, enlace_consulta=enlace,
                                           detalle="el documento no trae registro ni documento del profesional")
        registrado = self.por_registro(profesional.registro_profesional or "") or self.por_documento(profesional.numero_documento or "")
        if registrado is None:
            return VerificacionProfesional(estado="no_encontrado", fuente=FUENTE, enlace_consulta=enlace,
                                           detalle=f"registro {normalizar_registro(profesional.registro_profesional) or 'sin registro'} no está en el padrón")
        if not registrado.activo:
            return VerificacionProfesional(estado="no_encontrado", fuente=FUENTE, enlace_consulta=enlace,
                                           detalle=f"registro {registrado.registro} está inactivo en el padrón")
        if profesional.nombre and not nombres_compatibles(profesional.nombre, registrado.nombre):
            return VerificacionProfesional(estado="no_encontrado", fuente=FUENTE, enlace_consulta=enlace,
                                           detalle=f"registro {registrado.registro} pertenece a otro nombre en el padrón")
        consultado = registrado.registro_consultado_en.isoformat() if registrado.registro_consultado_en else None
        detalle = f"registro {registrado.registro} de {registrado.nombre}" + (
            f", {self.pack.identidad_profesional.registro} consultado el {registrado.registro_consultado_en:%d/%m/%Y}" if consultado
            else f", sin consulta en {self.pack.identidad_profesional.registro} anotada")
        return VerificacionProfesional(estado="verificado", fuente=FUENTE, enlace_consulta=enlace, detalle=detalle,
                                       consultado_en_registro_en=consultado)
