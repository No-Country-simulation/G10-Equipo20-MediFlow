"""Endpoints de documentos: ingesta JSON y multipart (RN-A), consulta (RN-I3), listado, original,
vista previa y entrega."""
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_llm, get_session, get_storage
from app.core.config import get_settings
from app.models.documento import Documento
from app.packs.loader import cargar_umbrales
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.request import CanalOrigen, CoberturaPaciente, DocumentoRequest
from app.services.archivos import MIME, ArchivoInvalido, contar_paginas, renderizar_pagina
from app.services.ingesta import ResultadoIngesta, ServicioIngesta
from app.services.llm import ClienteLLM, ServicioExtraccion
from app.services.orquestador import ErrorDeRevision, Orquestador
from app.services.storage import Storage

router = APIRouter(prefix="/documentos", tags=["documentos"])


def _orquestador(session: Session, storage: Storage, llm: ClienteLLM) -> Orquestador:
    settings = get_settings()
    return Orquestador(RepositorioDocumentos(session), storage, ServicioExtraccion(llm, max_intentos=settings.llm_max_intentos))


def _ingesta(session: Session, storage: Storage) -> ServicioIngesta:
    settings = get_settings()
    return ServicioIngesta(RepositorioDocumentos(session), storage, tamano_maximo_bytes=settings.tamano_maximo_bytes,
                           max_paginas_pdf=settings.max_paginas_pdf)


def _resumen(doc: Documento, *, con_resultado: bool = True) -> dict:
    resultado = doc.resultado_json
    datos = {
        "documento_id": doc.documento_id,
        "version": doc.version,
        "estado": doc.estado,
        "nivel_prioridad": doc.nivel_prioridad,
        "tipo_contenido": doc.tipo_contenido,
        "formato": doc.formato,
        "nombre_archivo": doc.nombre_archivo,
        "num_paginas": doc.num_paginas,
        "canal_origen": doc.canal_origen,
        "creado_en": doc.creado_en.isoformat() if doc.creado_en else None,
        "status_backup": resultado.get("status_backup") if resultado else doc.status_backup,
        "ruta_storage": resultado.get("ruta_storage") if resultado else doc.ruta_storage,
        "posible_duplicado_de": doc.posible_duplicado_de,
        "codigo_error": doc.codigo_error,
        "tipo": (resultado or {}).get("clasificacion", {}).get("tipo"),
        "motivo_auditoria": (resultado or {}).get("evaluacion", {}).get("motivo_auditoria"),
    }
    if con_resultado:
        datos["resultado"] = resultado
    return datos


def _responder_ingesta(ingesta: ResultadoIngesta, session: Session, storage: Storage, llm: ClienteLLM):
    doc = ingesta.documento
    if ingesta.duplicado_exacto:
        return JSONResponse({**_resumen(doc), "duplicado": True}, status_code=200)  # RN-O1
    if ingesta.codigo_error:
        return JSONResponse({**_resumen(doc), "codigo_error": ingesta.codigo_error}, status_code=400)  # RN-A1, RN-O5
    _orquestador(session, storage, llm).procesar(doc)
    return _resumen(doc)


@router.post("")
def recibir_documento(
    request: DocumentoRequest,
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
    llm: ClienteLLM = Depends(get_llm),
):
    return _responder_ingesta(_ingesta(session, storage).recibir(request), session, storage, llm)


@router.post("/archivo")
async def recibir_archivo(
    archivo: Annotated[UploadFile, File(description="PDF, PNG o JPG")],
    documento_id: Annotated[str, Form(min_length=1)],
    canal_origen: Annotated[CanalOrigen, Form()],
    cobertura_paciente: Annotated[CoberturaPaciente | None, Form()] = None,
    pais_origen: Annotated[str, Form(min_length=2, max_length=2)] = "CO",
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
    llm: ClienteLLM = Depends(get_llm),
):
    """Carga multipart validada por contenido (RN-A1). Mismo pipeline que la ruta JSON."""
    binario = await archivo.read()
    ingesta = _ingesta(session, storage).recibir_archivo(
        archivo.filename, binario, documento_id=documento_id.strip(), canal_origen=canal_origen.value,
        pais_origen=pais_origen.upper(), cobertura_paciente=cobertura_paciente.value if cobertura_paciente else None,
    )
    return _responder_ingesta(ingesta, session, storage, llm)


@router.get("")
def listar_documentos(
    estado: str | None = None,
    nivel: str | None = None,
    q: Annotated[str, Query(max_length=128)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: Session = Depends(get_session),
):
    documentos, total = RepositorioDocumentos(session).listar(estado=estado, nivel=nivel, q=q, limit=limit, offset=offset)
    return {"items": [_resumen(d, con_resultado=False) for d in documentos], "total": total, "limit": limit, "offset": offset}


def _documento_o_404(session: Session, documento_id: str) -> Documento:
    doc = RepositorioDocumentos(session).ultima_version(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="documento no encontrado")
    return doc


@router.get("/{documento_id}")
def consultar_documento(documento_id: str, session: Session = Depends(get_session)):
    doc = _documento_o_404(session, documento_id)
    return {
        **_resumen(doc),
        "pais_origen": doc.pais_origen,
        "paginas": doc.paginas_json or [],
        # RN-C3: confianza por campo que dio el LLM, junto con los umbrales vigentes de la sección 7.
        "confianzas": (doc.propuesta_json or {}).get("confianzas", {}),
        "umbrales": cargar_umbrales().confianza.model_dump(),
        # RN-M1: lo único que viajó al LLM. Sin mapa: nunca se expone.
        "texto_enviado_llm": doc.texto_seudonimizado,
        "entregas": doc.entregas_json or {},
        "verificaciones": doc.verificaciones_json or [],
        "autorizacion": doc.autorizacion_json,
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


@router.get("/{documento_id}/original")
def descargar_original(documento_id: str, session: Session = Depends(get_session), storage: Storage = Depends(get_storage)):
    """El original tal como llegó (RN-P1). Solo para revisores con acceso al documento (RN-K3)."""
    doc = _documento_o_404(session, documento_id)
    if not doc.ruta_storage:
        raise HTTPException(status_code=404, detail="original no respaldado")
    try:
        datos = storage.leer(doc.ruta_storage)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="original no disponible") from error
    tipo = MIME.get(doc.formato or "", "application/octet-stream")
    nombre = doc.nombre_archivo or doc.ruta_storage.rsplit("/", 1)[-1]
    return Response(datos, media_type=tipo, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                                     "Content-Disposition": f'inline; filename="{nombre}"'})


@router.get("/{documento_id}/vista_previa")
def vista_previa(
    documento_id: str,
    pagina: Annotated[int, Query(ge=1)] = 1,
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
):
    """PNG de una página del PDF original para la pantalla de revisión."""
    doc = _documento_o_404(session, documento_id)
    if doc.formato != "pdf":
        raise HTTPException(status_code=415, detail="la vista previa solo aplica a PDF")
    if not doc.ruta_storage:
        raise HTTPException(status_code=404, detail="original no respaldado")
    datos = storage.leer(doc.ruta_storage)
    try:
        png = renderizar_pagina(datos, pagina)
    except ArchivoInvalido as error:
        raise HTTPException(status_code=404 if error.codigo == "pagina_no_encontrada" else 422, detail=error.codigo) from error
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store", "X-Paginas": str(contar_paginas(datos))})


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
    doc = _documento_o_404(session, documento_id)
    try:
        return _orquestador(session, storage, llm).entregar(doc, cuerpo.destino)
    except ErrorDeRevision as error:
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
