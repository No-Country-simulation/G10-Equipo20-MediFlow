from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["salud"])


@router.get("/health")
def healthcheck() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "pack_pais": settings.pais_instalacion,
        "version_reglas": settings.version_reglas,
        "procesamiento": "worker" if settings.procesamiento_en_worker else "en_linea",
    }
