"""Métricas para el gestor (RN-R1, RN-R4, RN-R5, RN-T3). Sin datos del paciente (RN-M4)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.services.configuracion import ServicioConfiguracion
from app.services.metricas import calcular_metricas

router = APIRouter(prefix="/metricas", tags=["metricas"])


@router.get("")
def metricas(dias: int = Query(default=30, ge=1, le=3650), session: Session = Depends(get_session)):
    return calcular_metricas(session, ServicioConfiguracion(session).umbrales(), dias=dias)
