"""Acuse de alertas críticas (RN-J7, RN-Q5)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import cuenta_actual, firmante, get_llm, get_session, get_storage
from app.core.config import get_settings
from app.services.configuracion import ServicioConfiguracion
from app.repositories.documentos import RepositorioDocumentos
from app.services.llm import ClienteLLM, ServicioExtraccion
from app.services.orquestador import ErrorDeRevision, Orquestador
from app.services.storage import Storage

router = APIRouter(prefix="/alertas", tags=["alertas"])


@router.get("")
def listar_alertas(estado_acuse: str | None = None, session: Session = Depends(get_session)):
    """Alertas críticas para el banner y la bandeja del jefe de urgencias. Sin datos del paciente (RN-Q4)."""
    plazo = ServicioConfiguracion(session).umbrales().tiempos.escalamiento_sin_acuse_min
    salida = []
    for a in RepositorioDocumentos(session).listar_alertas(estado_acuse=estado_acuse):
        resultado = a.documento.resultado_json or {}
        hallazgos = resultado.get("extraccion", {}).get("hallazgos_criticos_detectados", [])
        salida.append({
            "documento_id": a.documento_id,
            "version": a.documento.version,
            "nivel": a.nivel,
            "canal": a.canal,
            "destinatario": a.destinatario,
            "mensaje": a.mensaje,
            "concepto": hallazgos[0] if hallazgos else None,
            "emitida_en": a.emitida_en.isoformat(),
            "plazo_minutos": plazo,
            "estado_acuse": a.estado_acuse,
            "acusado_por": a.acusado_por,
            "acusado_en": a.acusado_en.isoformat() if a.acusado_en else None,
            "estado_documento": a.documento.estado,
            "escalamientos": a.escalamientos or [],  # RN-F2, RN-P7
        })
    return salida


@router.post("/{documento_id}/acuse")
def acusar(
    documento_id: str,
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
    llm: ClienteLLM = Depends(get_llm),
    cuenta=Depends(cuenta_actual),
):
    quien = firmante(session, cuenta, "acusar_alerta")  # RN-Q5: el acuse lo da la cuenta de la sesión
    repo = RepositorioDocumentos(session)
    doc = repo.ultima_version(documento_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="documento no encontrado")
    orquestador = Orquestador(repo, storage, ServicioExtraccion(llm, max_intentos=get_settings().llm_max_intentos))
    try:
        return orquestador.acusar(doc, quien.usuario)
    except ErrorDeRevision as error:
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
