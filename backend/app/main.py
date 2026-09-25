from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.documents import router as documents_router

app = FastAPI(title="MediFlow API", version="0.1.0")
app.include_router(health_router)
app.include_router(documents_router)


@app.get("/config", tags=["configuration"])
def public_config():
    from app.core.config import get_settings
    settings = get_settings()
    return {"default_country": settings.default_country, "timezone": settings.app_timezone,
            "max_upload_bytes": settings.max_upload_bytes, "authentication": "local_without_auth"}
