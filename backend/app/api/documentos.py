"""Endpoints de documentos: ingesta (RN-A) y consulta del estado (RN-I3)."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_storage
from app.core.config import get_settings
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.request import DocumentoRequest
from app.services.ingesta import ServicioIngesta
from app.services.storage import Storage

router = APIRouter(prefix="/documentos", tags=["documentos"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def recibir_documento(
    request: DocumentoRequest,
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    servicio = ServicioIngesta(
        RepositorioDocumentos(session), storage, tamano_maximo_bytes=get_settings().tamano_maximo_bytes
    )
    resultado = servicio.recibir(request)
    doc = resultado.documento
    cuerpo = {
        "documento_id": doc.documento_id,
        "version": doc.version,
        "estado": doc.estado,
        "status_backup": doc.status_backup,
        "ruta_storage": doc.ruta_storage,
        "posible_duplicado_de": doc.posible_duplicado_de,
    }
    if resultado.duplicado_exacto:
        # RN-O1: se devuelve el resultado previo con 200; no se reprocesa.
        return JSONResponse({**cuerpo, "duplicado": True, "resultado": doc.resultado_json}, status_code=200)
    if resultado.codigo_error:
        # RN-A1, RN-O5: rechazo explícito. El documento quedó guardado (RN-P1).
        return JSONResponse({**cuerpo, "codigo_error": resultado.codigo_error}, status_code=400)
    return cuerpo


@router.get("/{documento_id}")
def consultar_documento(documento_id: str, session: Session = Depends(get_session)):
    doc = RepositorioDocumentos(session).ultima_version(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="documento no encontrado")
    return {
        "documento_id": doc.documento_id,
        "version": doc.version,
        "estado": doc.estado,
        "canal_origen": doc.canal_origen,
        "pais_origen": doc.pais_origen,
        "status_backup": doc.status_backup,
        "ruta_storage": doc.ruta_storage,
        "posible_duplicado_de": doc.posible_duplicado_de,
        "codigo_error": doc.codigo_error,
        "resultado": doc.resultado_json,
        "transiciones": [
            {
                "de_estado": t.de_estado,
                "a_estado": t.a_estado,
                "actor": t.actor,
                "motivo": t.motivo,
                "fecha_hora": t.fecha_hora.isoformat(),
            }
            for t in doc.transiciones
        ],
    }
