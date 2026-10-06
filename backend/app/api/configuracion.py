"""Configuración de la instalación para el gestor (RN-L1 a RN-L6). Quien configura no revisa (RN-K2)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import cuenta_actual, firmante, get_llm, get_session, get_storage
from app.core.config import get_settings
from app.models.gobierno import VersionConfiguracion
from app.packs.loader import cargar_pack, cargar_umbrales
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.resultado import Destino
from app.services.configuracion import (CONFIGURABLES, DESTINOS_PROTEGIDOS, CambiosConfiguracion, ErrorConfiguracion, ServicioConfiguracion,
                                        aprobaciones_requeridas, valor_base)
from app.services.llm import ClienteLLM, ServicioExtraccion
from app.services.orquestador import Orquestador
from app.services.storage import Storage

router = APIRouter(prefix="/configuracion", tags=["configuracion"])


class PropuestaRequest(BaseModel):
    cambios: CambiosConfiguracion
    motivo: str = ""


class SimulacionRequest(BaseModel):
    cambios: CambiosConfiguracion
    ultimos: int | None = Field(default=None, ge=1, le=500)


class RechazoRequest(BaseModel):
    motivo: str = ""


def _gestor(session: Session, cuenta) -> str:
    """RN-K2: solo el gestor configura, y firma con su sesión."""
    return firmante(session, cuenta, "configurar").usuario


def _version(v: VersionConfiguracion) -> dict:
    return {
        "id": v.id,
        "numero": v.numero,
        "autor": v.autor,
        "motivo": v.motivo,
        "cambios": v.cambios_json,
        "simulacion": v.simulacion_json,
        "toca_seguridad": v.toca_seguridad,
        "aprobaciones": v.aprobaciones_json or [],
        "aprobaciones_requeridas": aprobaciones_requeridas(v.toca_seguridad),
        "estado": v.estado,
        "creado_en": v.creado_en.isoformat() if v.creado_en else None,
        "vigente_desde": v.vigente_desde.isoformat() if v.vigente_desde else None,
        "vigente_hasta": v.vigente_hasta.isoformat() if v.vigente_hasta else None,
        "cierre_por": v.cierre_por,
        "cierre_motivo": v.cierre_motivo,
    }


def _orquestador(session: Session, storage: Storage, llm: ClienteLLM) -> Orquestador:
    return Orquestador(RepositorioDocumentos(session), storage, ServicioExtraccion(llm, max_intentos=get_settings().llm_max_intentos))


def _simular(servicio: ServicioConfiguracion, orq: Orquestador, cambios: CambiosConfiguracion, ultimos: int | None) -> dict:
    return servicio.simular(cambios, pais=get_settings().pais_instalacion, ultimos=ultimos or cargar_umbrales().calidad.simulacion_ultimos,
                            recalcular=lambda doc, pack, umbrales: orq.recalcular(doc, pack=pack, umbrales=umbrales))


@router.get("")
def configuracion(session: Session = Depends(get_session)):
    servicio = ServicioConfiguracion(session)
    base = cargar_umbrales()
    efectivos = servicio.umbrales()
    pais = get_settings().pais_instalacion
    pack_base = cargar_pack(pais)
    pack = servicio.pack(pais)
    vigente = servicio.vigente()
    return {
        "vigente": _version(vigente) if vigente else {"id": None, "numero": 0, "autor": "sistema", "motivo": "valores iniciales de la sección 7",
                                                       "cambios": {"umbrales": {}, "ampliaciones": {}, "destinos_inactivos": None}, "vigente_desde": None, "estado": "vigente"},
        "umbrales_base": base.model_dump(exclude={"news2", "rangos", "calidad"}),
        "umbrales_efectivos": efectivos.model_dump(exclude={"news2", "rangos", "calidad"}),
        "rangos": {clave: {**base.rangos[clave].model_dump(), "base": valor_base(base, clave), "efectivo": valor_base(efectivos, clave)}
                   for clave in CONFIGURABLES if clave in base.rangos},
        "no_configurable": {"news2": base.news2.model_dump(exclude={"configurable"})},
        "listas": {
            "alto_riesgo": {"base": pack_base.medicamentos.alto_riesgo, "ampliadas": pack.medicamentos.alto_riesgo[len(pack_base.medicamentos.alto_riesgo):]},
            "control_especial": {"base": pack_base.medicamentos.control_especial, "ampliadas": pack.medicamentos.control_especial[len(pack_base.medicamentos.control_especial):]},
            "hallazgos_criticos": {"base": [h.concepto for h in pack_base.hallazgos_criticos],
                                   "ampliados": [h.concepto for h in pack.hallazgos_criticos[len(pack_base.hallazgos_criticos):]]},
        },
        # RN-L1: destinos que la clínica usa. Los protegidos se muestran y no se pueden desactivar (RN-L2).
        "destinos": [{"destino": d.value, "activo": d.value not in pack.destinos_inactivos, "protegido": d in DESTINOS_PROTEGIDOS} for d in Destino],
        "calidad": base.calidad.model_dump(),
        "propuestas": [_version(v) for v in servicio.propuestas()],
        "historial": [_version(v) for v in servicio.historial()],
    }


@router.post("/simular")
def simular(cuerpo: SimulacionRequest, session: Session = Depends(get_session), storage: Storage = Depends(get_storage), llm: ClienteLLM = Depends(get_llm)):
    """RN-L6: qué habría cambiado sobre los últimos documentos. No persiste nada."""
    try:
        return _simular(ServicioConfiguracion(session), _orquestador(session, storage, llm), cuerpo.cambios, cuerpo.ultimos)
    except ErrorConfiguracion as error:
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error


@router.post("/propuestas", status_code=201)
def proponer(cuerpo: PropuestaRequest, session: Session = Depends(get_session), storage: Storage = Depends(get_storage), llm: ClienteLLM = Depends(get_llm),
             cuenta=Depends(cuenta_actual)):
    usuario = _gestor(session, cuenta)
    servicio = ServicioConfiguracion(session)
    try:
        simulacion = _simular(servicio, _orquestador(session, storage, llm), cuerpo.cambios, None)
        v = servicio.proponer(cuerpo.cambios, autor=usuario, motivo=cuerpo.motivo, pais=get_settings().pais_instalacion, simulacion=simulacion)
    except ErrorConfiguracion as error:
        session.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
    return _version(v)


@router.post("/propuestas/{id_}/aprobar")
def aprobar(id_: int, session: Session = Depends(get_session), cuenta=Depends(cuenta_actual)):
    usuario = _gestor(session, cuenta)
    try:
        return _version(ServicioConfiguracion(session).aprobar(id_, usuario, pais=get_settings().pais_instalacion))
    except ErrorConfiguracion as error:
        session.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error


@router.post("/propuestas/{id_}/rechazar")
def rechazar(id_: int, cuerpo: RechazoRequest, session: Session = Depends(get_session), cuenta=Depends(cuenta_actual)):
    usuario = _gestor(session, cuenta)
    try:
        return _version(ServicioConfiguracion(session).rechazar(id_, usuario, cuerpo.motivo))
    except ErrorConfiguracion as error:
        session.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
