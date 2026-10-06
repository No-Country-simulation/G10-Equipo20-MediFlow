"""Métricas para el gestor (RN-R1, RN-R4, RN-R5, RN-T3) y conjunto de referencia (RN-R2). Sin datos del paciente (RN-M4)."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.services.configuracion import ServicioConfiguracion
from app.services.metricas import calcular_metricas
from app.services.referencia import ServicioReferencia, caso_como_dict

router = APIRouter(prefix="/metricas", tags=["metricas"])


@router.get("")
def metricas(dias: int = Query(default=30, ge=1, le=3650), session: Session = Depends(get_session)):
    return calcular_metricas(session, ServicioConfiguracion(session).umbrales(), dias=dias)


@router.get("/referencia")
def referencia(limit: int = Query(default=200, ge=1, le=2000), session: Session = Depends(get_session)):
    """RN-R2: el conjunto de referencia, seudonimizado. Resumen y últimos casos."""
    servicio = ServicioReferencia(session)
    return {"resumen": servicio.resumen(), "casos": [caso_como_dict(c) for c in servicio.listar(limit=limit)]}


@router.get("/referencia/exportar")
def exportar_referencia(session: Session = Depends(get_session)):
    """RN-R2, RN-R3: el conjunto completo, con el texto y la propuesta que vio el LLM (con tokens), para medir un cambio antes de sacarlo."""
    casos = [caso_como_dict(c, completo=True) for c in ServicioReferencia(session).todos()]
    return JSONResponse(casos, headers={"Content-Disposition": 'attachment; filename="conjunto_referencia.json"'})
