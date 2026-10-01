from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.api import administracion, alertas, auth, autorizaciones, configuracion, documentos, farmacia, healthcheck, metricas, pacientes, resumen, revision
from app.api.deps import ROLES_CLINICOS, acceso
from app.core.config import get_settings
from app.core.database import crear_tablas


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    crear_tablas()
    yield


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
