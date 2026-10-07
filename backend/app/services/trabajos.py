"""Cola persistente de procesamiento en la propia base, sin broker (RN-P2, RN-P5).

La petición que recibe un documento termina al guardar el original (RN-P1) y deja un trabajo EN_COLA. Un worker
aparte lo reclama con `FOR UPDATE SKIP LOCKED`, lo arrienda por un rato y renueva el arriendo mientras trabaja.
Si el worker cae, el arriendo vence y otro worker retoma el trabajo. Un fallo del motor reencola con espera creciente;
agotados los intentos, el documento sigue la ruta de fallo técnico: revisión humana con la detección determinística
y su alerta si hay hallazgo (RN-P4). Las tablas propias siguen siendo la verdad (RN-I3): el trabajo solo ordena.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.documento import Documento
from app.models.trabajo import TrabajoProcesamiento
from app.schemas.resultado import EstadoDocumento as E
from app.services.orquestador import Orquestador

logger = logging.getLogger(__name__)

VIVOS = ("EN_COLA", "EN_CURSO")
ESPERA_BASE_S = 15  # tras un fallo: 15 s, 30 s, 60 s...
ESTADOS_QUE_PROCESA = (E.RECIBIDO, E.VALIDADO)
ESTADOS_INTERMEDIOS = (E.RECIBIDO, E.VALIDADO, E.CLASIFICADO, E.EXTRAIDO, E.EVALUADO)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class ServicioTrabajos:
    def __init__(self, session: Session, *, arriendo_s: int | None = None, intentos_maximos: int | None = None):
        settings = get_settings()
        self.session = session
        self.arriendo_s = arriendo_s or settings.worker_arriendo_s
        self.intentos_maximos = intentos_maximos or settings.worker_intentos_maximos

    # --- consulta ------------------------------------------------------------------------

    def vivo(self, documento: Documento) -> TrabajoProcesamiento | None:
        return self.session.scalars(select(TrabajoProcesamiento).where(TrabajoProcesamiento.documento_pk == documento.id,
                                                                       TrabajoProcesamiento.estado.in_(VIVOS))).first()

    def ultimo(self, documento: Documento) -> TrabajoProcesamiento | None:
        return self.session.scalars(select(TrabajoProcesamiento).where(TrabajoProcesamiento.documento_pk == documento.id)
                                    .order_by(TrabajoProcesamiento.id.desc())).first()

    def pendientes(self) -> int:
        """Trabajos que todavía no terminaron: lo que la cola tiene por delante."""
        return len(self.session.scalars(select(TrabajoProcesamiento.id).where(TrabajoProcesamiento.estado.in_(VIVOS))).all())

    # --- lado de la API -------------------------------------------------------------------

    def encolar(self, documento: Documento, *, solicitado_por: str | None = None) -> TrabajoProcesamiento:
        """Idempotente: si el documento ya tiene un trabajo vivo, lo devuelve. Solo entra lo que el grafo puede empezar."""
        if documento.estado not in ESTADOS_QUE_PROCESA:
            raise ValueError(f"solo se encola un documento RECIBIDO o VALIDADO; está en {documento.estado}")
        existente = self.vivo(documento)
        if existente is not None:
            return existente
        trabajo = TrabajoProcesamiento(documento_pk=documento.id, documento_id=documento.documento_id, solicitado_por=solicitado_por)
        self.session.add(trabajo)
        self.session.flush()
        return trabajo

    # --- lado del worker ------------------------------------------------------------------

    def reclamar(self, ahora: datetime | None = None) -> TrabajoProcesamiento | None:
        """Toma el trabajo más antiguo que esté en cola y le llegó su turno, o uno en curso cuyo arriendo venció
        (el worker que lo tenía cayó). Varios workers a la vez se reparten por `SKIP LOCKED`."""
        ahora = ahora or _ahora()
        consulta = (
            select(TrabajoProcesamiento)
            .where(or_((TrabajoProcesamiento.estado == "EN_COLA") & (TrabajoProcesamiento.proximo_intento_en <= ahora),
                       (TrabajoProcesamiento.estado == "EN_CURSO") & (TrabajoProcesamiento.arrendado_hasta < ahora)))
            .order_by(TrabajoProcesamiento.creado_en, TrabajoProcesamiento.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        trabajo = self.session.scalars(consulta).first()
        if trabajo is None:
            self.session.commit()
            return None
        if trabajo.estado == "EN_CURSO":
            logger.warning("Trabajo %s del documento %s: arriendo vencido; otro worker lo retoma", trabajo.id, trabajo.documento_id)  # RN-M4: solo el ID
        trabajo.estado = "EN_CURSO"
        trabajo.token = str(uuid.uuid4())
        trabajo.intento += 1
        trabajo.arrendado_hasta = ahora + timedelta(seconds=self.arriendo_s)
        trabajo.actualizado_en = ahora
        self.session.commit()
        return trabajo

    def renovar(self, trabajo_id: int, token: str, ahora: datetime | None = None) -> bool:
        """Latido del worker: extiende el arriendo mientras el trabajo siga siendo suyo."""
        trabajo = self.session.get(TrabajoProcesamiento, trabajo_id)
        if trabajo is None or trabajo.token != token or trabajo.estado != "EN_CURSO":
            return False
        ahora = ahora or _ahora()
        trabajo.arrendado_hasta = ahora + timedelta(seconds=self.arriendo_s)
        trabajo.actualizado_en = ahora
        self.session.commit()
        return True

    def terminar(self, trabajo: TrabajoProcesamiento, *, token: str, error: str | None = None, ahora: datetime | None = None) -> None:
        """Cierra el trabajo: TERMINADO, o reencolado con espera creciente, o FALLIDO al agotar los intentos.
        Si el arriendo ya pasó a otro worker (token distinto), este no toca nada."""
        if trabajo.token != token:
            logger.warning("Trabajo %s: el arriendo ya es de otro worker; no se cierra desde aquí", trabajo.id)
            return
        ahora = ahora or _ahora()
        trabajo.actualizado_en = ahora
        trabajo.arrendado_hasta = None
        trabajo.token = None
        if error is None:
            trabajo.estado, trabajo.codigo_error = "TERMINADO", None
        elif trabajo.intento >= self.intentos_maximos:
            trabajo.estado, trabajo.codigo_error = "FALLIDO", error[:300]
        else:
            trabajo.estado, trabajo.codigo_error = "EN_COLA", error[:300]
            trabajo.proximo_intento_en = ahora + timedelta(seconds=ESPERA_BASE_S * 2 ** (trabajo.intento - 1))
        self.session.commit()


def atender(session: Session, trabajo: TrabajoProcesamiento, orquestador: Orquestador, servicio: ServicioTrabajos,
            ahora: datetime | None = None) -> Documento:
    """Corre el grafo del documento del trabajo. Lo que ya está confirmado en la base manda: un documento todavía
    RECIBIDO o VALIDADO empieza su hilo; uno que otro proceso dejó a mitad (estado intermedio confirmado) lo retoma;
    uno que ya salió de esas etapas no necesita nada. Un fallo reencola o, agotados los intentos, abre la ruta de fallo técnico."""
    token = trabajo.token
    doc = session.get(Documento, trabajo.documento_pk)
    try:
        if doc.estado in ESTADOS_QUE_PROCESA:
            orquestador.procesar(doc)
        elif doc.estado in ESTADOS_INTERMEDIOS:
            orquestador.reanudar(doc)
    except Exception as error:  # noqa: BLE001 - cualquier caída del motor se registra en el trabajo, nunca se pierde el documento
        session.rollback()
        motivo = f"{type(error).__name__}: {str(error)[:200]}"
        logger.warning("Trabajo %s del documento %s falló en el intento %d: %s", trabajo.id, trabajo.documento_id, trabajo.intento, type(error).__name__)
        trabajo = session.get(TrabajoProcesamiento, trabajo.id)
        doc = session.get(Documento, trabajo.documento_pk)
        servicio.terminar(trabajo, token=token, error=motivo, ahora=ahora)
        if trabajo.estado == "FALLIDO" and doc.estado in ESTADOS_INTERMEDIOS:
            orquestador.fallar(doc, motivo)  # RN-P2, RN-P4
        return doc
    servicio.terminar(trabajo, token=token, ahora=ahora)
    return doc
