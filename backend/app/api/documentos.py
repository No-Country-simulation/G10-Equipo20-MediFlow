"""Endpoints de documentos: ingesta y pipeline (RN-A a RN-G), consulta (RN-I3) y entrega."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_llm, get_session, get_storage
from app.core.config import get_settings
from app.models.documento import Documento
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.request import DocumentoRequest
from app.services.ingesta import ServicioIngesta
from app.services.llm import ClienteLLM, ServicioExtraccion
from app.services.orquestador import ErrorDeRevision, Orquestador
from app.services.storage import Storage

router = APIRouter(prefix="/documentos", tags=["documentos"])


def _orquestador(session: Session, storage: Storage, llm: ClienteLLM) -> Orquestador:
    settings = get_settings()
    return Orquestador(RepositorioDocumentos(session), storage, ServicioExtraccion(llm, max_intentos=settings.llm_max_intentos))


def _resumen(doc: Documento) -> dict:
    resultado = doc.resultado_json
    return {
        "documento_id": doc.documento_id,
        "version": doc.version,
        "estado": doc.estado,
        "nivel_prioridad": doc.nivel_prioridad,
        "status_backup": resultado.get("status_backup") if resultado else doc.status_backup,
        "ruta_storage": resultado.get("ruta_storage") if resultado else doc.ruta_storage,
        "posible_duplicado_de": doc.posible_duplicado_de,
        "codigo_error": doc.codigo_error,
        "resultado": resultado,
    }


@router.post("")
def recibir_documento(
    request: DocumentoRequest,
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
    llm: ClienteLLM = Depends(get_llm),
):
    repo = RepositorioDocumentos(session)
    ingesta = ServicioIngesta(repo, storage, tamano_maximo_bytes=get_settings().tamano_maximo_bytes).recibir(request)
    doc = ingesta.documento
    if ingesta.duplicado_exacto:
        return JSONResponse({**_resumen(doc), "duplicado": True}, status_code=200)  # RN-O1
    if ingesta.codigo_error:
        return JSONResponse({**_resumen(doc), "codigo_error": ingesta.codigo_error}, status_code=400)  # RN-A1, RN-O5
    _orquestador(session, storage, llm).procesar(doc)
    return _resumen(doc)


@router.get("/{documento_id}")
def consultar_documento(documento_id: str, session: Session = Depends(get_session)):
    doc = RepositorioDocumentos(session).ultima_version(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="documento no encontrado")
    return {
        **_resumen(doc),
        "canal_origen": doc.canal_origen,
        "pais_origen": doc.pais_origen,
        "entregas": doc.entregas_json or {},
        "alerta": _alerta(doc),
        "correcciones": [
            {"campo": c.campo, "extraido": c.extraido, "corregido": c.corregido, "usuario": c.usuario} for c in doc.correcciones
        ],
        "transiciones": [
            {"de_estado": t.de_estado, "a_estado": t.a_estado, "actor": t.actor, "motivo": t.motivo, "fecha_hora": t.fecha_hora.isoformat()}
            for t in doc.transiciones
        ],
    }


def _alerta(doc: Documento) -> dict | None:
    alerta = next((a for a in doc.alertas if a.nivel == "Crítico"), None)
    if alerta is None:
        return None
    return {"nivel": alerta.nivel, "canal": alerta.canal, "destinatario": alerta.destinatario, "mensaje": alerta.mensaje,
            "estado_acuse": alerta.estado_acuse, "acusado_por": alerta.acusado_por, "emitida_en": alerta.emitida_en.isoformat()}


class EntregaRequest(BaseModel):
    destino: str


@router.post("/{documento_id}/entregar")
def confirmar_entrega(
    documento_id: str,
    cuerpo: EntregaRequest,
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
    llm: ClienteLLM = Depends(get_llm),
):
    doc = RepositorioDocumentos(session).ultima_version(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="documento no encontrado")
    try:
        return _orquestador(session, storage, llm).entregar(doc, cuerpo.destino)
    except ErrorDeRevision as error:
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
