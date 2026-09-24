from datetime import UTC, datetime

from app.models.document import Document
from app.schemas.lifecycle import DocumentStatus as S, StateEvent
from app.services.errors import DocumentError

# La evaluacion puede detectar contenido insuficiente antes de extraer campos.
TRANSITIONS = {
    S.RECIBIDO: {S.VALIDADO, S.RECHAZADO},
    S.VALIDADO: {S.CLASIFICADO, S.EVALUADO, S.FALLO_TECNICO},
    S.CLASIFICADO: {S.EXTRAIDO, S.EVALUADO, S.FALLO_TECNICO},
    S.EXTRAIDO: {S.EVALUADO, S.FALLO_TECNICO},
    S.EVALUADO: {S.EN_REVISION_HUMANA, S.ENRUTADO, S.FALLO_TECNICO},
    S.FALLO_TECNICO: {S.VALIDADO, S.CLASIFICADO, S.EXTRAIDO, S.EN_REVISION_HUMANA},
    S.EN_REVISION_HUMANA: {S.RESUELTO},
    S.RESUELTO: {S.ENRUTADO},
    S.ENRUTADO: {S.ENTREGADO, S.FALLO_TECNICO},
    S.ENTREGADO: set(),
    S.RECHAZADO: set(),
}


def initialize_history(document: Document) -> None:
    document.status = S.RECIBIDO.value
    document.processing_attempts = 0
    document.state_history = [StateEvent(
        status=S.RECIBIDO, occurred_at=document.received_at, reason="UPLOAD_RECEIVED",
    ).model_dump(mode="json")]


def transition(document: Document, target: S, reason: str) -> None:
    current = S(document.status)
    if current == target:
        return
    if target not in TRANSITIONS[current]:
        raise DocumentError(409, f"INVALID_STATE_TRANSITION:{current.value}->{target.value}")
    document.status = target.value
    document.state_history = [*(document.state_history or []), StateEvent(
        status=target, occurred_at=datetime.now(UTC), reason=reason,
        attempt=document.processing_attempts or 0,
    ).model_dump(mode="json")]
