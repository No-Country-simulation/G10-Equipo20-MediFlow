from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Indica que la API esta operativa; no comprueba servicios externos."""
    return HealthResponse(status="ok", service="mediflow-api")
