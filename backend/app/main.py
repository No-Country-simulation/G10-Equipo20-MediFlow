import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app.api import administracion, alertas, auth, autorizaciones, configuracion, documentos, farmacia, healthcheck, metricas, pacientes, resumen, revision
from app.api.deps import ROLES_CLINICOS, acceso, get_memoria
from app.core.config import get_settings
from app.core.arranque import preparar_instalacion
from app.core.database import crear_tablas, get_engine
from app.services.escalamiento import escalar_una_vuelta

logger = logging.getLogger(__name__)


async def _bucle_de_escalamiento(cada_s: int) -> None:
    """RN-F2: las alertas sin acuse escalan solas, aunque nadie tenga la bandeja abierta."""
    while True:
        await asyncio.sleep(cada_s)
        try:
            await asyncio.to_thread(escalar_una_vuelta)
        except Exception:  # noqa: BLE001 - una vuelta fallida no detiene las siguientes
            logger.exception("Fallo en la vuelta de escalamiento de alertas")


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    crear_tablas()
    with Session(get_engine()) as sesion:
        informe = preparar_instalacion(sesion)  # roles de la tabla K y, si la instalación lo pide, cuentas de demostración
    if informe["roles"] or informe["cuentas"]:
        logger.info("Instalación preparada: %d roles y %d cuentas de demostración creados", informe["roles"], informe["cuentas"])
    get_memoria()  # la memoria del grafo abre su conexión y crea sus tablas al arrancar, no en la primera petición
    cada_s = get_settings().escalamiento_cada_s
    tarea = asyncio.create_task(_bucle_de_escalamiento(cada_s)) if cada_s > 0 else None
    yield
    if tarea is not None:
        tarea.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.version_reglas, lifespan=ciclo_de_vida)
    app.include_router(healthcheck.router)
    app.include_router(auth.router)
    # RN-K2: con sesión, cada sección la ve solo el rol que la necesita. Sin sesión rige EXIGIR_SESION.
    clinico = [Depends(acceso(*ROLES_CLINICOS))]
    for seccion in (documentos, revision, alertas, farmacia, autorizaciones):
        app.include_router(seccion.router, dependencies=clinico)
    app.include_router(pacientes.router, dependencies=[Depends(acceso("auditor_clinico"))])
    app.include_router(resumen.router, dependencies=[Depends(acceso())])
    app.include_router(configuracion.router, dependencies=[Depends(acceso("gestor"))])
    app.include_router(metricas.router, dependencies=[Depends(acceso("gestor"))])
    app.include_router(administracion.router, dependencies=[Depends(acceso("administrador"))])
    return app


app = create_app()
