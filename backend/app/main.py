import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.administration import router as administration_router
from app.api.health import router as health_router
from app.api.documents import router as documents_router
from app.api.destinations import router as destinations_router
from app.api.patients import router as patients_router
from app.api.auth import router as auth_router
from app.api.execution import router as execution_router
from app.core.countries import COUNTRIES
from app.core.document_catalog import document_catalog
from app.core.request_limits import RequestBodyLimitMiddleware

logger = logging.getLogger("mediflow")


def run_db_migrations():
    try:
        from alembic import command
        from alembic.config import Config
        logger.info("Verificando y ejecutando migraciones de base de datos...")
        base_dir = Path(__file__).resolve().parent.parent
        ini_path = base_dir / "alembic.ini"
        if not ini_path.is_file():
            ini_path = Path("alembic.ini")
        alembic_cfg = Config(str(ini_path))
        alembic_cfg.set_main_option("script_location", str(base_dir / "migrations"))
        command.upgrade(alembic_cfg, "head")
        logger.info("Migraciones ejecutadas exitosamente.")
    except Exception as e:
        logger.error(f"Error al ejecutar migraciones: {e}")


def run_bootstrap_admin():
    try:
        from app.core.config import get_settings
        settings = get_settings()
        pwd = settings.admin_bootstrap_password.get_secret_value() if settings.admin_bootstrap_password else ""
        if settings.admin_bootstrap_email and pwd:
            logger.info("Ejecutando bootstrap de cuenta administradora...")
            from app.core.bootstrap_admin import main as bootstrap_main
            bootstrap_main()
            logger.info("Bootstrap de administrador finalizado exitosamente.")
    except Exception as e:
        logger.error(f"Error en bootstrap de administrador: {e}")


def start_embedded_worker():
    if os.environ.get("RUN_EMBEDDED_WORKER") == "1":
        try:
            logger.info("Iniciando worker en segundo plano...")
            from app.worker import main as worker_main
            worker_thread = threading.Thread(target=worker_main, daemon=True)
            worker_thread.start()
            logger.info("Worker en segundo plano iniciado correctamente.")
        except Exception as e:
            logger.error(f"Error al iniciar worker embebido: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_db_migrations()
    run_bootstrap_admin()
    start_embedded_worker()
    yield


app = FastAPI(title="MediFlow API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestBodyLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https://.*\.onrender\.com$|^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(execution_router)
app.include_router(administration_router)
app.include_router(health_router)
app.include_router(documents_router)
app.include_router(destinations_router)
app.include_router(patients_router)
app.include_router(auth_router)


@app.get("/document-types", tags=["configuration"])
def types_catalog():
    return document_catalog()


@app.get("/countries", tags=["configuration"])
def countries():
    return [{"code": code, "name": name} for code, name in COUNTRIES]


@app.get("/config", tags=["configuration"])
def public_config():
    from app.core.config import get_settings
    settings = get_settings()
    return {
        "default_country": settings.default_country,
        "timezone": settings.app_timezone,
        "max_upload_bytes": settings.max_upload_bytes,
        "authentication": "local_accounts",
    }
