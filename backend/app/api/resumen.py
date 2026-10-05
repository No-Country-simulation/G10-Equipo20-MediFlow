"""Contadores para el inicio de cada rol."""
from collections import Counter
from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_llm, get_session, get_storage
from app.core.config import get_settings
from app.repositories.documentos import RepositorioDocumentos
from app.services.llm import ClienteLLM, ServicioExtraccion
from app.services.orquestador import Orquestador
from app.services.storage import Storage

router = APIRouter(prefix="/resumen", tags=["resumen"])


@router.get("")
def resumen(session: Session = Depends(get_session), storage: Storage = Depends(get_storage), llm: ClienteLLM = Depends(get_llm)):
    repo = RepositorioDocumentos(session)
    orq = Orquestador(repo, storage, ServicioExtraccion(llm, max_intentos=get_settings().llm_max_intentos))
    documentos = repo.ultimas_versiones()
    por_estado = Counter(d.estado for d in documentos)
    por_prioridad = Counter(d.nivel_prioridad for d in documentos if d.nivel_prioridad)
    enrutados = [d for d in documentos if d.estado == "ENRUTADO"]
    inicio_dia = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    return {
        "total": len(documentos),
        "por_estado": dict(por_estado),
        "por_prioridad": dict(por_prioridad),
        "en_revision": por_estado.get("EN_REVISION_HUMANA", 0),
        "alertas_sin_acuse": len(repo.listar_alertas(estado_acuse="pendiente")),
        "recetas_por_verificar": sum(1 for d in enrutados if orq.es_receta_por_verificar(d)),
        "ordenes_por_autorizar": sum(1 for d in enrutados if orq.es_orden_por_autorizar(d)),
        "enrutados": len(enrutados),
        "entregados_hoy": repo.entregados_desde(inicio_dia),
    }
