"""Solicitudes del titular (RN-M6): una persona revisa una decisión automatizada cuando el paciente lo pide.

El paciente no entra al sistema: la solicitud la registra el auditor clínico en su ficha, con quién la presentó
y por qué canal. El plazo para responder lo fija el pack (en Colombia, Ley 1581 de 2012, art. 15). La respuesta
la firma la cuenta que revisó, y dice si la decisión se mantiene o se corrigió.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documento import Documento
from app.models.paciente import Paciente, SolicitudTitular
from app.packs.modelos import PackPais
from app.services.errores import ErrorDeRevision

PRESENTADA_POR = ("titular", "representante")
CANALES = ("presencial", "telefono", "correo", "escrito")
RESULTADOS = ("mantenida", "corregida")


def vencimiento(desde: datetime, dias_habiles: int) -> datetime:
    """Cuenta días hábiles de lunes a viernes a partir del día siguiente. Los festivos no se descuentan."""
    fecha = desde
    restantes = dias_habiles
    while restantes > 0:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5:
            restantes -= 1
    return fecha


class ServicioSolicitudesTitular:
    def __init__(self, session: Session, pack: PackPais | None = None):
        self.session = session
        self.pack = pack

    def registrar(self, paciente_id: int, *, documento_id: str, presentada_por: str, canal: str, motivo: str, usuario: str) -> SolicitudTitular:
        if self.pack is None:
            raise ValueError("registrar exige el pack de la instalación para el plazo")
        paciente = self.session.get(Paciente, paciente_id)
        if paciente is None:
            raise ErrorDeRevision(404, "paciente no encontrado")
        if presentada_por not in PRESENTADA_POR:
            raise ErrorDeRevision(422, f"quién la presenta: {', '.join(PRESENTADA_POR)}")
        if canal not in CANALES:
            raise ErrorDeRevision(422, f"canal: {', '.join(CANALES)}")
        if not motivo.strip():
            raise ErrorDeRevision(422, "RN-M6: la solicitud exige el motivo del titular")
        documento = self.session.scalars(
            select(Documento).where(Documento.documento_id == documento_id.strip(), Documento.paciente_id == paciente_id)
            .order_by(Documento.version.desc())
        ).first()
        if documento is None:
            raise ErrorDeRevision(422, "el documento no está en la ficha de este paciente")
        if self.pendiente_de_documento(documento.documento_id) is not None:
            raise ErrorDeRevision(409, "ya hay una solicitud pendiente sobre este documento")
        ahora = datetime.now(timezone.utc)
        solicitud = SolicitudTitular(
            paciente_id=paciente_id, documento_id=documento.documento_id, version=documento.version, presentada_por=presentada_por,
            canal=canal, motivo=motivo.strip(), registrada_por=usuario.strip(), registrada_en=ahora,
            vence_en=vencimiento(ahora, self.pack.datos_personales.plazo_reclamo_dias_habiles),
        )
        self.session.add(solicitud)
        self.session.commit()
        self.session.refresh(solicitud)
        return solicitud

    def responder(self, solicitud_id: int, *, resultado: str, respuesta: str, usuario: str) -> SolicitudTitular:
        solicitud = self.session.get(SolicitudTitular, solicitud_id)
        if solicitud is None:
            raise ErrorDeRevision(404, "solicitud no encontrada")
        if solicitud.estado != "pendiente":
            raise ErrorDeRevision(409, "la solicitud ya fue respondida")
        if resultado not in RESULTADOS:
            raise ErrorDeRevision(422, f"resultado: {', '.join(RESULTADOS)}")
        if not respuesta.strip():
            raise ErrorDeRevision(422, "RN-M6: la respuesta al titular no puede quedar vacía")
        solicitud.estado = "respondida"
        solicitud.resultado = resultado
        solicitud.respuesta = respuesta.strip()
        solicitud.respondida_por = usuario.strip()
        solicitud.respondida_en = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(solicitud)
        return solicitud

    def de_paciente(self, paciente_id: int) -> list[SolicitudTitular]:
        return list(self.session.scalars(select(SolicitudTitular).where(SolicitudTitular.paciente_id == paciente_id)
                                         .order_by(SolicitudTitular.id.desc())))

    def listar(self, estado: str = "pendiente") -> list[tuple[SolicitudTitular, Paciente]]:
        """Pendientes primero por vencimiento; las respondidas, de la más reciente a la más antigua."""
        consulta = select(SolicitudTitular, Paciente).join(Paciente, Paciente.id == SolicitudTitular.paciente_id)
        if estado != "todas":
            consulta = consulta.where(SolicitudTitular.estado == estado)
        orden = (SolicitudTitular.vence_en, SolicitudTitular.id) if estado == "pendiente" else (SolicitudTitular.id.desc(),)
        return [(s, p) for s, p in self.session.execute(consulta.order_by(*orden))]

    def pendiente_de_documento(self, documento_id: str) -> SolicitudTitular | None:
        return self.session.scalars(select(SolicitudTitular).where(SolicitudTitular.documento_id == documento_id,
                                                                  SolicitudTitular.estado == "pendiente")).first()
