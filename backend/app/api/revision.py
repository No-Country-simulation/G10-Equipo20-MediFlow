"""Cola y acciones de revisión humana (RN-J1 a RN-J8, RN-G4)."""
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import cuenta_actual, firmante, get_llm, get_memoria, get_notificador, get_session, get_storage
from app.core.config import get_settings
from app.services.configuracion import ServicioConfiguracion
from app.repositories.documentos import RepositorioDocumentos
from app.services.alertas import Notificador
from app.services.llm import ClienteLLM, ServicioExtraccion
from app.services.orquestador import ErrorDeRevision, Orquestador
from app.services.revision_humana import ServicioRevision, plazo_minutos
from app.services.storage import Storage

router = APIRouter(prefix="/revision", tags=["revision humana"])


@router.get("")
def cola_de_revision(session: Session = Depends(get_session)):
    documentos = RepositorioDocumentos(session).en_revision()
    cola = ServicioConfiguracion(session).umbrales().tiempos.cola_revision
    return [
        {
            "documento_id": d.documento_id,
            "version": d.version,
            "nivel_prioridad": d.nivel_prioridad,
            "motivo_auditoria": (d.resultado_json or {}).get("evaluacion", {}).get("motivo_auditoria"),
            "campos_dudosos": (d.resultado_json or {}).get("evaluacion", {}).get("campos_dudosos", []),
            "tipo": (d.resultado_json or {}).get("clasificacion", {}).get("tipo"),
            # Conceptos del pack (TEP_AGUDO…), nunca texto del paciente (RN-M4): la cola muestra qué es cada caso.
            "hallazgos": (d.resultado_json or {}).get("extraccion", {}).get("hallazgos_criticos_detectados", []),
            "creado_en": d.creado_en.isoformat(),
            "plazo_minutos": plazo_minutos(d.nivel_prioridad, cola),
            "asignado_a": d.asignado_a,  # RN-J3
            "escalado_a_rol": d.escalado_a_rol,  # RN-J2, RN-J3
        }
        for d in documentos
    ]


@router.get("/revisores")
def revisores(session: Session = Depends(get_session)):
    """RN-J3: a quién se puede reasignar un caso. Sin claves ni hashes: solo cuenta, nombre y rol."""
    return [{"usuario": u.usuario, "nombre": u.nombre, "rol": u.rol} for u in ServicioRevision(RepositorioDocumentos(session)).revisores()]


class ResolucionRequest(BaseModel):
    accion: Literal["aprobar", "corregir", "rechazar", "transcribir", "reasignar", "escalar"]  # RN-J3
    motivo: str = ""
    version: int | None = None  # RN-O2: la versión que la persona tenía en pantalla; si llegó otra, no se decide a ciegas
    asignar_a: str | None = None  # reasignar: cuenta del revisor que toma el caso
    correcciones: dict[str, Any] | None = None
    # Fallo técnico (RN-P2): sin lectura del LLM, la persona transcribe con la misma forma de la propuesta.
    transcripcion: dict[str, Any] | None = None


@router.post("/{documento_id}/resolver")
def resolver(
    documento_id: str,
    cuerpo: ResolucionRequest,
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
    llm: ClienteLLM = Depends(get_llm),
    notificador: Notificador = Depends(get_notificador),
    cuenta=Depends(cuenta_actual),
):
    quien = firmante(session, cuenta, "resolver_revision")  # RN-G4, RN-K5: firma la cuenta de la sesión
    repo = RepositorioDocumentos(session)
    doc = repo.ultima_version(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="documento no encontrado")
    if cuerpo.version is not None and cuerpo.version != doc.version:
        raise HTTPException(status_code=409, detail=f"RN-O2: llegó la versión {doc.version} de este documento mientras revisabas la {cuerpo.version}; "
                                                    "recarga el caso y decide sobre la versión nueva")
    try:
        if cuerpo.accion == "reasignar":  # RN-J3: no decide nada; el grafo sigue esperando a la persona
            resultado = ServicioRevision(repo).reasignar(doc, usuario=quien.usuario, rol=quien.rol, a_usuario=cuerpo.asignar_a or "", motivo=cuerpo.motivo)
        elif cuerpo.accion == "escalar":
            resultado = ServicioRevision(repo).escalar(doc, usuario=quien.usuario, rol=quien.rol, motivo=cuerpo.motivo)
        else:
            orquestador = Orquestador(repo, storage, ServicioExtraccion(llm, max_intentos=get_settings().llm_max_intentos), memoria=get_memoria(),
                                      notificador=notificador)
            resultado = orquestador.resolver_revision(
                doc, accion=cuerpo.accion, usuario=quien.usuario, rol=quien.rol, motivo=cuerpo.motivo, correcciones=cuerpo.correcciones,
                transcripcion=cuerpo.transcripcion,
            )
    except ErrorDeRevision as error:
        session.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
    return {"documento_id": doc.documento_id, "version": doc.version, "estado": doc.estado, "resultado": resultado.model_dump(mode="json")}
