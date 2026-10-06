"""Una vuelta del trabajo periódico de alertas (RN-F2, RN-P7): lo llama la API cada tanto y el script a mano."""
import logging

from sqlalchemy.orm import Session

from app.core.database import get_engine
from app.repositories.documentos import RepositorioDocumentos
from app.services.alertas import Notificador, ServicioAlertas
from app.services.configuracion import ServicioConfiguracion

logger = logging.getLogger(__name__)


def escalar_una_vuelta(session: Session | None = None, notificador: Notificador | None = None) -> list[str]:
    """Escala las alertas sin acuse vencidas y devuelve los IDs de documento escalados."""
    if notificador is None:
        from app.api.deps import get_notificador  # noqa: PLC0415 - evita import circular

        notificador = get_notificador()
    if session is not None:
        return _vuelta(session, notificador)
    with Session(get_engine()) as sesion:
        return _vuelta(sesion, notificador)


def _vuelta(session: Session, notificador: Notificador) -> list[str]:
    repo = RepositorioDocumentos(session)
    servicio = ServicioAlertas(repo, ServicioConfiguracion(session).umbrales(), notificador)
    escaladas = [a.documento_id for a in servicio.escalar_vencidas()]
    if escaladas:
        logger.info("RN-F2: %d alertas escaladas: %s", len(escaladas), ", ".join(escaladas))
    return escaladas
