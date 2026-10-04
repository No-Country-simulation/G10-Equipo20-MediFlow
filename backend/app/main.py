from fastapi import FastAPI

from app.api.administration import router as administration_router
from app.api.health import router as health_router
from app.api.documents import router as documents_router
from app.api.destinations import router as destinations_router
from app.api.patients import router as patients_router
from app.api.auth import router as auth_router
from app.core.countries import COUNTRIES
from app.core.document_catalog import document_catalog

app = FastAPI(title="MediFlow API", version="0.1.0")
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
    return {"default_country": settings.default_country, "timezone": settings.app_timezone,
            "max_upload_bytes": settings.max_upload_bytes, "authentication": "local_accounts"}
