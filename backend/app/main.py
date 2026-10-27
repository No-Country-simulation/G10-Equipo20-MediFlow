import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

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

db_creation_status = {"status": "pending"}
migration_status = {"status": "pending", "error": None}
bootstrap_status = {"status": "pending", "error": None}


def ensure_database_exists():
    """Ensure target database exists in postgres cluster; create it if missing."""
    global db_creation_status
    from app.core.config import get_settings
    from sqlalchemy import create_engine, text
    import traceback

    try:
        settings = get_settings()
        target_db = settings.postgres_db
        # Connect to 'postgres' maintenance database with autocommit
        m_url = settings.database_url.set(database="postgres")
        m_engine = create_engine(m_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
        with m_engine.connect() as conn:
            rows = conn.execute(text("SELECT datname FROM pg_database WHERE datistemplate = false;")).fetchall()
            cluster_dbs = [r[0] for r in rows]
            logger.info(f"Bases de datos encontradas en cluster: {cluster_dbs}")

            if target_db not in cluster_dbs:
                logger.info(f"Creando base de datos '{target_db}'...")
                conn.execute(text(f'CREATE DATABASE "{target_db}"'))
                logger.info(f"Base de datos '{target_db}' creada exitosamente.")
                cluster_dbs.append(target_db)

        m_engine.dispose()
        db_creation_status = {"status": "ok", "cluster_dbs": cluster_dbs, "target": target_db}
    except Exception as e:
        logger.error(f"Error en ensure_database_exists: {e}\n{traceback.format_exc()}")
        db_creation_status = {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


def run_db_migrations():
    global migration_status
    ensure_database_exists()
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
        migration_status = {"status": "ok", "error": None}
        logger.info("Migraciones ejecutadas exitosamente.")
    except Exception as e:
        import traceback
        migration_status = {"status": "error", "error": str(e), "traceback": traceback.format_exc()}
        logger.error(f"Error al ejecutar migraciones: {e}\n{traceback.format_exc()}")


def run_bootstrap_admin():
    global bootstrap_status
    try:
        from app.core.config import get_settings
        settings = get_settings()
        email = str(settings.admin_bootstrap_email or '').strip()
        pwd = settings.admin_bootstrap_password.get_secret_value() if settings.admin_bootstrap_password else ''

        # Set default bootstrap credentials if not supplied via Render dashboard
        if not email or not pwd:
            os.environ.setdefault("ADMIN_BOOTSTRAP_EMAIL", "admin@mediflow.com")
            os.environ.setdefault("ADMIN_BOOTSTRAP_PASSWORD", "AdminMediflow2026!")
            get_settings.cache_clear()

        logger.info("Ejecutando bootstrap de cuenta administradora...")
        from app.core.bootstrap_admin import main as bootstrap_main
        bootstrap_main()
        bootstrap_status = {"status": "ok", "error": None}
        logger.info("Bootstrap de administrador finalizado exitosamente.")
    except Exception as e:
        import traceback
        bootstrap_status = {"status": "error", "error": str(e), "traceback": traceback.format_exc()}
        logger.error(f"Error en bootstrap de administrador: {e}\n{traceback.format_exc()}")


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


@app.get("/diagnostic", tags=["debug"])
def diagnostic():
    import traceback
    from app.core.database import get_engine
    from app.core.config import get_settings

    res = {
        "db_creation": db_creation_status,
        "migrations": migration_status,
        "bootstrap": bootstrap_status,
    }
    try:
        s = get_settings()
        res["settings"] = {
            "postgres_host": s.postgres_host,
            "postgres_port": s.postgres_port,
            "postgres_db": s.postgres_db,
            "postgres_user": s.postgres_user,
            "admin_email": s.admin_bootstrap_email,
            "has_admin_pwd": bool(s.admin_bootstrap_password.get_secret_value() if s.admin_bootstrap_password else False),
        }
    except Exception as e:
        res["settings_error"] = str(e)

    try:
        engine = get_engine()
        with engine.connect() as conn:
            tables = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public';")).fetchall()
            res["tables"] = [t[0] for t in tables]
            if "accounts" in res["tables"]:
                accounts = conn.execute(text("SELECT email, role, active FROM accounts;")).fetchall()
                res["accounts"] = [{"email": a[0], "role": a[1], "active": a[2]} for a in accounts]
    except Exception as e:
        res["db_query_error"] = str(e)
        res["db_query_traceback"] = traceback.format_exc()

    return res


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
