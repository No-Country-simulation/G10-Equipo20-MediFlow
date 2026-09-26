from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import alertas, autorizaciones, documentos, farmacia, healthcheck, resumen, revision
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
    app.include_router(documentos.router)
    app.include_router(revision.router)
    app.include_router(alertas.router)
    app.include_router(farmacia.router)
    app.include_router(autorizaciones.router)
    app.include_router(resumen.router)
    return app


app = create_app()
