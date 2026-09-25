"""Acuse de alertas críticas (RN-J7, RN-Q5)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_llm, get_session, get_storage
from app.core.config import get_settings
from app.repositories.documentos import RepositorioDocumentos
from app.services.llm import ClienteLLM, ServicioExtraccion
from app.services.orquestador import ErrorDeRevision, Orquestador
from app.services.storage import Storage

router = APIRouter(prefix="/alertas", tags=["alertas"])


class AcuseRequest(BaseModel):
    usuario: str


@router.post("/{documento_id}/acuse")
def acusar(
    documento_id: str,
    cuerpo: AcuseRequest,
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
        return orquestador.acusar(doc, cuerpo.usuario)
    except ErrorDeRevision as error:
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
