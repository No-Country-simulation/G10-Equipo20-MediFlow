"""Directorio de pacientes (RN-M6): localizar todo lo asociado a una persona y registrar las solicitudes del titular.
Solo para roles clínicos (RN-K1, RN-K2)."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import cuenta_actual, firmante, get_session
from app.core.config import get_settings
from app.models.documento import Documento
from app.models.paciente import Paciente, SolicitudTitular
from app.services.configuracion import ServicioConfiguracion
from app.services.errores import ErrorDeRevision
from app.services.pacientes import ServicioPacientes
from app.services.solicitudes_titular import ServicioSolicitudesTitular

router = APIRouter(prefix="/pacientes", tags=["pacientes"])


def _ficha(paciente: Paciente, documentos: int) -> dict:
    return {
        "id": paciente.id, "pais": paciente.pais, "tipo_documento": paciente.tipo_documento, "numero_documento": paciente.numero_documento,
        "nombre": paciente.nombre, "edad": paciente.edad, "sexo": paciente.sexo, "documentos": documentos,
        "creado_en": paciente.creado_en.isoformat() if paciente.creado_en else None,
        "actualizado_en": paciente.actualizado_en.isoformat() if paciente.actualizado_en else None,
    }


def _documento(doc: Documento) -> dict:
    resultado = doc.resultado_json or {}
    return {
        "documento_id": doc.documento_id, "version": doc.version, "estado": doc.estado, "nivel_prioridad": doc.nivel_prioridad,
        "tipo": resultado.get("clasificacion", {}).get("tipo"),
        "fecha_documento": resultado.get("extraccion", {}).get("fecha_documento"),
        "creado_en": doc.creado_en.isoformat() if doc.creado_en else None,
    }


def solicitud_como_dict(s: SolicitudTitular, paciente: Paciente | None = None) -> dict:
    datos = {
        "id": s.id, "paciente_id": s.paciente_id, "documento_id": s.documento_id, "version": s.version,
        "presentada_por": s.presentada_por, "canal": s.canal, "motivo": s.motivo,
        "registrada_por": s.registrada_por, "registrada_en": s.registrada_en.isoformat(), "vence_en": s.vence_en.isoformat(),
        "estado": s.estado, "resultado": s.resultado, "respuesta": s.respuesta, "respondida_por": s.respondida_por,
        "respondida_en": s.respondida_en.isoformat() if s.respondida_en else None,
    }
    if paciente is not None:
        datos["paciente_nombre"] = paciente.nombre
    return datos


@router.get("/solicitudes")
def listar_solicitudes(estado: Literal["pendiente", "respondida", "todas"] = "pendiente", session: Session = Depends(get_session)):
    """RN-M6: las solicitudes del titular, pendientes primero por vencimiento."""
    return [solicitud_como_dict(s, p) for s, p in ServicioSolicitudesTitular(session).listar(estado)]


class SolicitudRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documento_id: str = Field(..., min_length=1, max_length=128)
    presentada_por: Literal["titular", "representante"] = "titular"
    canal: Literal["presencial", "telefono", "correo", "escrito"] = "presencial"
    motivo: str = Field(..., max_length=2000)


class RespuestaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resultado: Literal["mantenida", "corregida"]
    respuesta: str = Field(..., max_length=4000)


@router.post("/{paciente_id}/solicitudes", status_code=201)
def registrar_solicitud(paciente_id: int, cuerpo: SolicitudRequest, session: Session = Depends(get_session), cuenta=Depends(cuenta_actual)):
    """RN-M6: el auditor registra, en la ficha, que el titular pide revisión humana de una decisión automatizada."""
    quien = firmante(session, cuenta, "editar_paciente")
    pack = ServicioConfiguracion(session).pack(get_settings().pais_instalacion)
    try:
        solicitud = ServicioSolicitudesTitular(session, pack).registrar(
            paciente_id, documento_id=cuerpo.documento_id, presentada_por=cuerpo.presentada_por, canal=cuerpo.canal,
            motivo=cuerpo.motivo, usuario=quien.usuario,
        )
    except ErrorDeRevision as error:
        session.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
    return solicitud_como_dict(solicitud)


@router.post("/solicitudes/{solicitud_id}/responder")
def responder_solicitud(solicitud_id: int, cuerpo: RespuestaRequest, session: Session = Depends(get_session), cuenta=Depends(cuenta_actual)):
    """RN-M6: la respuesta es una revisión humana y la firma quien resuelve la revisión (RN-G4)."""
    quien = firmante(session, cuenta, "resolver_revision")
    try:
        solicitud = ServicioSolicitudesTitular(session).responder(solicitud_id, resultado=cuerpo.resultado, respuesta=cuerpo.respuesta, usuario=quien.usuario)
    except ErrorDeRevision as error:
        session.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
    return solicitud_como_dict(solicitud)


@router.get("")
def listar_pacientes(
    q: Annotated[str, Query(max_length=128)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: Session = Depends(get_session),
):
    filas, total = ServicioPacientes(session).listar(q=q, limit=limit, offset=offset)
    return {"items": [_ficha(p, n) for p, n in filas], "total": total, "limit": limit, "offset": offset}


@router.get("/{paciente_id}")
def consultar_paciente(paciente_id: int, session: Session = Depends(get_session)):
    servicio = ServicioPacientes(session)
    paciente = session.get(Paciente, paciente_id)
    if paciente is None:
        raise HTTPException(status_code=404, detail="paciente no encontrado")
    documentos = servicio.documentos(paciente_id)
    return {**_ficha(paciente, servicio.contar_documentos(paciente_id)), "historial": paciente.historial_json or [],
            "documentos_listado": [_documento(d) for d in documentos],
            "solicitudes": [solicitud_como_dict(s) for s in ServicioSolicitudesTitular(session).de_paciente(paciente_id)]}


class EdicionPaciente(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str = ""  # RN-G4: quién lo cambió sale de la sesión; aquí solo el porqué
    nombre: str | None = Field(default=None, max_length=255)
    edad: int | None = Field(default=None, ge=0, le=130)
    sexo: str | None = Field(default=None, max_length=16)


@router.patch("/{paciente_id}")
def editar_paciente(paciente_id: int, cuerpo: EdicionPaciente, session: Session = Depends(get_session), cuenta=Depends(cuenta_actual)):
    """Corrige un dato mal registrado (por ejemplo, un nombre con error que genera conflictos). El número de documento no se edita."""
    quien = firmante(session, cuenta, "editar_paciente")  # RN-K2: solo el auditor clínico
    cambios = cuerpo.model_dump(exclude_unset=True, exclude={"motivo"})
    try:
        if not cambios:
            raise ErrorDeRevision(422, "no hay nada que cambiar")
        servicio = ServicioPacientes(session)
        paciente = servicio.editar(paciente_id, usuario=quien.usuario, motivo=cuerpo.motivo, cambios=cambios)
    except ErrorDeRevision as error:
        session.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
    return {**_ficha(paciente, servicio.contar_documentos(paciente.id)), "historial": paciente.historial_json or []}
