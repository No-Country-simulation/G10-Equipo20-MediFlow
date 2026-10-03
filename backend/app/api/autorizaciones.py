"""Bandeja de Auditoría de autorizaciones (RN-E5, RN-E9, RN-CO12, RN-CO13)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import cuenta_actual, firmante, get_llm, get_session, get_storage
from app.core.config import get_settings
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.resultado import Destino as D, ResultadoTriaje
from app.services.llm import ClienteLLM, ServicioExtraccion
from app.services.orquestador import ErrorDeRevision, Orquestador
from app.services.storage import Storage

router = APIRouter(prefix="/autorizaciones", tags=["autorizaciones"])


def _orquestador(session: Session, storage: Storage, llm: ClienteLLM) -> Orquestador:
    return Orquestador(RepositorioDocumentos(session), storage, ServicioExtraccion(llm, max_intentos=get_settings().llm_max_intentos))


def _fila(doc, r: ResultadoTriaje) -> dict:
    return {
        "documento_id": doc.documento_id,
        "version": doc.version,
        "nivel_prioridad": doc.nivel_prioridad,
        "canal_origen": doc.canal_origen,
        "creado_en": doc.creado_en.isoformat() if doc.creado_en else None,
        "cobertura": doc.cobertura_paciente,
        "motivo_destino": r.enrutamiento.motivos_destino.get(D.AUDITORIA_AUTORIZACIONES.value),
        "documentacion_incompleta": r.enrutamiento.documentacion_incompleta,
        "procedimientos": [p.texto for p in r.extraccion.procedimientos],
        "cups": [p.cups for p in r.extraccion.procedimientos if p.cups],
        "diagnosticos": [f"{d.texto} {d.cie10_sugerido or ''}".strip() for d in r.extraccion.diagnosticos],
        "justificacion": r.enrutamiento.justificacion_enrutamiento,
        "fecha_documento": r.extraccion.fecha_documento,
    }


@router.get("")
def bandeja(session: Session = Depends(get_session), storage: Storage = Depends(get_storage), llm: ClienteLLM = Depends(get_llm)):
    """Órdenes por autorizar (destino principal Auditoría) y avisos de urgencias (RN-CO13), sin datos del paciente."""
    orq = _orquestador(session, storage, llm)
    por_autorizar, avisos = [], []
    for doc in orq.repo.ultimas_versiones(estado="ENRUTADO"):
        if not orq.es_orden_por_autorizar(doc):
            continue
        r = ResultadoTriaje.model_validate(doc.resultado_json)
        fila = _fila(doc, r)
        if r.enrutamiento.destino_principal is D.AUDITORIA_AUTORIZACIONES:
            por_autorizar.append(fila)
        else:
            avisos.append(fila)
    return {"por_autorizar": por_autorizar, "avisos_urgencias": avisos}


class ResolucionAutorizacion(BaseModel):
    accion: Literal["aprobar", "devolver"]
    motivo: str = ""


@router.post("/{documento_id}/resolver")
def resolver(documento_id: str, cuerpo: ResolucionAutorizacion, session: Session = Depends(get_session),
             storage: Storage = Depends(get_storage), llm: ClienteLLM = Depends(get_llm), cuenta=Depends(cuenta_actual)):
    quien = firmante(session, cuenta, "resolver_autorizacion")
    orq = _orquestador(session, storage, llm)
    doc = orq.repo.ultima_version(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="documento no encontrado")
    try:
        return orq.resolver_autorizacion(doc, accion=cuerpo.accion, usuario=quien.usuario, motivo=cuerpo.motivo)
    except ErrorDeRevision as error:
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
