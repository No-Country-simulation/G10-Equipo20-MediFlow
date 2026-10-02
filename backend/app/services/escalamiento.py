"""Una vuelta del trabajo periódico de alertas (RN-F2, RN-P7): lo llama la API cada tanto y el script a mano."""
import logging

from sqlalchemy.orm import Session

from app.core.database import get_engine
from app.repositories.documentos import RepositorioDocumentos
from app.services.alertas import NotificadorRegistro, ServicioAlertas
from app.services.configuracion import ServicioConfiguracion

logger = logging.getLogger(__name__)


def escalar_una_vuelta(session: Session | None = None) -> list[str]:
    """Escala las alertas sin acuse vencidas y devuelve los IDs de documento escalados."""
    if session is not None:
        return _vuelta(session)
    with Session(get_engine()) as sesion:
        return _vuelta(sesion)


def _vuelta(session: Session) -> list[str]:
    repo = RepositorioDocumentos(session)
    servicio = ServicioAlertas(repo, ServicioConfiguracion(session).umbrales(), NotificadorRegistro())
    escaladas = [a.documento_id for a in servicio.escalar_vencidas()]
    if escaladas:
        logger.info("RN-F2: %d alertas escaladas: %s", len(escaladas), ", ".join(escaladas))
    return escaladas
