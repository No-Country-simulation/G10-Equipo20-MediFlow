"""Cola y acciones de revisión humana (RN-J1 a RN-J8, RN-G4)."""
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_llm, get_session, get_storage
from app.core.config import get_settings
from app.packs.loader import cargar_umbrales
from app.repositories.documentos import RepositorioDocumentos
from app.services.llm import ClienteLLM, ServicioExtraccion
from app.services.orquestador import ErrorDeRevision, Orquestador
from app.services.storage import Storage

router = APIRouter(prefix="/revision", tags=["revision humana"])


def _plazo_minutos(nivel: str | None) -> int:
    """RN-J2: Crítico 15 min, Urgente 2 h, Rutina 24 h hábiles."""
    cola = cargar_umbrales().tiempos.cola_revision
    if nivel == "Crítico":
        return cola.critico_min
    if nivel == "Urgente":
        return cola.urgente_h * 60
    return cola.rutina_h_habiles * 60


@router.get("")
def cola_de_revision(session: Session = Depends(get_session)):
    documentos = RepositorioDocumentos(session).en_revision()
    return [
        {
            "documento_id": d.documento_id,
            "version": d.version,
            "nivel_prioridad": d.nivel_prioridad,
            "motivo_auditoria": (d.resultado_json or {}).get("evaluacion", {}).get("motivo_auditoria"),
            "campos_dudosos": (d.resultado_json or {}).get("evaluacion", {}).get("campos_dudosos", []),
            "tipo": (d.resultado_json or {}).get("clasificacion", {}).get("tipo"),
            "creado_en": d.creado_en.isoformat(),
            "plazo_minutos": _plazo_minutos(d.nivel_prioridad),
        }
        for d in documentos
    ]


class ResolucionRequest(BaseModel):
    accion: Literal["aprobar", "corregir", "rechazar"]  # RN-J3 (reasignar y escalar quedan para después)
    usuario: str = Field(..., min_length=1)  # RN-G4, RN-K5
    rol: str = Field(..., min_length=1)
    motivo: str = ""
    correcciones: dict[str, Any] | None = None


@router.post("/{documento_id}/resolver")
def resolver(
    documento_id: str,
    cuerpo: ResolucionRequest,
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
    llm: ClienteLLM = Depends(get_llm),
):
    repo = RepositorioDocumentos(session)
    doc = repo.ultima_version(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="documento no encontrado")
    orquestador = Orquestador(repo, storage, ServicioExtraccion(llm, max_intentos=get_settings().llm_max_intentos))
    try:
        resultado = orquestador.resolver_revision(
            doc, accion=cuerpo.accion, usuario=cuerpo.usuario, rol=cuerpo.rol, motivo=cuerpo.motivo, correcciones=cuerpo.correcciones
        )
    except ErrorDeRevision as error:
        session.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
    return {"documento_id": doc.documento_id, "version": doc.version, "estado": doc.estado, "resultado": resultado.model_dump(mode="json")}
