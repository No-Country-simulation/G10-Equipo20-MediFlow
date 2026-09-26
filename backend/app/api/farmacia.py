"""Cola de Farmacia y doble verificación (RN-E6, RN-J6, RN-CO9)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_llm, get_session, get_storage
from app.core.config import get_settings
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.resultado import ResultadoTriaje
from app.services.llm import ClienteLLM, ServicioExtraccion
from app.services.orquestador import ErrorDeRevision, Orquestador
from app.services.storage import Storage

router = APIRouter(prefix="/farmacia", tags=["farmacia"])

_ORDEN_NIVEL = {"Crítico": 0, "Urgente": 1, "Rutina": 2}


def _orquestador(session: Session, storage: Storage, llm: ClienteLLM) -> Orquestador:
    return Orquestador(RepositorioDocumentos(session), storage, ServicioExtraccion(llm, max_intentos=get_settings().llm_max_intentos))


@router.get("")
def cola_farmacia(session: Session = Depends(get_session), storage: Storage = Depends(get_storage), llm: ClienteLLM = Depends(get_llm)):
    """Recetas enrutadas a Farmacia pendientes de verificación. Alto riesgo y control especial primero. Sin datos del paciente."""
    orq = _orquestador(session, storage, llm)
    filas = []
    for doc in orq.repo.ultimas_versiones(estado="ENRUTADO"):
        if not orq.es_receta_por_verificar(doc):
            continue
        r = ResultadoTriaje.model_validate(doc.resultado_json)
        alto = any(m.alto_riesgo for m in r.extraccion.medicamentos)
        control = any(m.control_especial for m in r.extraccion.medicamentos)
        filas.append({
            "documento_id": doc.documento_id,
            "version": doc.version,
            "nivel_prioridad": doc.nivel_prioridad,
            "creado_en": doc.creado_en.isoformat() if doc.creado_en else None,
            "medicamentos": [m.model_dump() for m in r.extraccion.medicamentos],
            "alto_riesgo": alto,
            "control_especial": control,
            "verificaciones_requeridas": orq.verificaciones_requeridas(r),
            "verificaciones": [{"orden": v["orden"], "usuario": v["usuario"]} for v in (doc.verificaciones_json or [])],
            "motivo_destino": r.enrutamiento.motivos_destino.get("Farmacia_Hospitalaria"),
            "fecha_documento": r.extraccion.fecha_documento,
        })
    filas.sort(key=lambda f: (not (f["alto_riesgo"] or f["control_especial"]), _ORDEN_NIVEL.get(f["nivel_prioridad"] or "Rutina", 2), f["creado_en"] or ""))
    return filas


class VerificacionRequest(BaseModel):
    usuario: str


@router.post("/{documento_id}/verificar")
def verificar(documento_id: str, cuerpo: VerificacionRequest, session: Session = Depends(get_session),
              storage: Storage = Depends(get_storage), llm: ClienteLLM = Depends(get_llm)):
    orq = _orquestador(session, storage, llm)
    doc = orq.repo.ultima_version(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="documento no encontrado")
    try:
        return orq.verificar_farmacia(doc, cuerpo.usuario)
    except ErrorDeRevision as error:
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
