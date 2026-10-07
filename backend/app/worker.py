"""Worker de procesamiento: `python -m app.worker`.

Toma trabajos de la cola persistente (app/services/trabajos.py), corre el grafo del documento y renueva su arriendo
con un latido mientras trabaja. Pueden correr varios a la vez: la base los reparte. Se detiene limpio con SIGTERM:
termina el trabajo que tiene entre manos y no toma otro.
"""
import logging
import signal
import threading

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.api.deps import get_llm, get_memoria, get_notificador, get_storage
from app.core.config import get_settings
from app.core.database import get_engine
from app.repositories.documentos import RepositorioDocumentos
from app.services.llm import ServicioExtraccion
from app.services.orquestador import Orquestador
from app.services.trabajos import ServicioTrabajos, atender

logger = logging.getLogger(__name__)


def _orquestador(session: Session) -> Orquestador:
    settings = get_settings()
    return Orquestador(RepositorioDocumentos(session), get_storage(), ServicioExtraccion(get_llm(), max_intentos=settings.llm_max_intentos),
                       memoria=get_memoria(), notificador=get_notificador())


def _latir(engine: Engine, trabajo_id: int, token: str, detener: threading.Event, arriendo_s: int) -> None:
    """Renueva el arriendo en su propia conexión; si el trabajo ya no es nuestro, deja de latir."""
    cada_s = max(5, arriendo_s // 5)
    while not detener.wait(cada_s):
        try:
            with Session(engine) as sesion:
                if not ServicioTrabajos(sesion).renovar(trabajo_id, token):
                    return
        except Exception:  # noqa: BLE001 - sin base no hay latido; el arriendo vence y otro worker retoma
            logger.warning("Trabajo %s: latido sin respuesta de la base", trabajo_id)


def una_vuelta(engine: Engine) -> bool:
    """Atiende a lo sumo un trabajo. Devuelve si hubo alguno que atender."""
    with Session(engine) as sesion:
        servicio = ServicioTrabajos(sesion)
        trabajo = servicio.reclamar()
        if trabajo is None:
            return False
        logger.info("Trabajo %s: documento %s, intento %d", trabajo.id, trabajo.documento_id, trabajo.intento)  # RN-M4: solo el ID
        detener = threading.Event()
        latido = threading.Thread(target=_latir, args=(engine, trabajo.id, trabajo.token, detener, servicio.arriendo_s), daemon=True)
        latido.start()
        try:
            doc = atender(sesion, trabajo, _orquestador(sesion), servicio)
        finally:
            detener.set()
            latido.join(timeout=5)
        logger.info("Trabajo %s: documento %s quedó en %s", trabajo.id, trabajo.documento_id, doc.estado)
        return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parar = threading.Event()
    for senal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(senal, lambda *_: parar.set())
    settings = get_settings()
    engine = get_engine()
    get_memoria()  # la memoria del grafo abre su conexión al arrancar, no en el primer trabajo
    logger.info("Worker de procesamiento listo (arriendo %d s, %d intentos)", settings.worker_arriendo_s, settings.worker_intentos_maximos)
    while not parar.is_set():
        try:
            hubo = una_vuelta(engine)
        except Exception:  # noqa: BLE001 - base o storage caídos: se espera y se vuelve a intentar
            logger.exception("Vuelta del worker fallida; se reintenta")
            hubo = False
        if not hubo:
            parar.wait(settings.worker_espera_s)
    logger.info("Worker detenido")


if __name__ == "__main__":
    main()
