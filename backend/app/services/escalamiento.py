"""Una vuelta del trabajo periódico de escalamiento (RN-F2, RN-P7, RN-J2): lo llama la API cada tanto y el script a mano."""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.database import get_engine
from app.repositories.documentos import RepositorioDocumentos
from app.services.alertas import Notificador, ServicioAlertas
from app.services.configuracion import ServicioConfiguracion
from app.services.revision_humana import ServicioRevision

logger = logging.getLogger(__name__)


def escalar_una_vuelta(session: Session | None = None, notificador: Notificador | None = None, ahora: datetime | None = None) -> list[str]:
    """Escala las alertas sin acuse vencidas (RN-F2) y los casos de revisión con el plazo vencido (RN-J2).
    Devuelve los IDs de documento escalados."""
    if notificador is None:
        from app.api.deps import get_notificador  # noqa: PLC0415 - evita import circular

        notificador = get_notificador()
    if session is not None:
        return _vuelta(session, notificador, ahora)
    with Session(get_engine()) as sesion:
        return _vuelta(sesion, notificador, ahora)


def _vuelta(session: Session, notificador: Notificador, ahora: datetime | None) -> list[str]:
    repo = RepositorioDocumentos(session)
    umbrales = ServicioConfiguracion(session).umbrales()
    escaladas = [a.documento_id for a in ServicioAlertas(repo, umbrales, notificador).escalar_vencidas(ahora)]
    if escaladas:
        logger.info("RN-F2: %d alertas escaladas: %s", len(escaladas), ", ".join(escaladas))
    vencidas = [d.documento_id for d in ServicioRevision(repo).escalar_vencidas(umbrales.tiempos.cola_revision, ahora)]
    if vencidas:
        logger.info("RN-J2: %d casos de revisión escalados: %s", len(vencidas), ", ".join(vencidas))
    return escaladas + vencidas
