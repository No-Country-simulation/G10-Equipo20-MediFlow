from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.graph.processing import build_processing_graph
from app.models.document import Document
from app.providers.base import DocumentProvider, ProviderError
from app.schemas.lifecycle import DocumentStatus as S
from app.schemas.processing import ProcessingResult
from app.services.errors import DocumentError
from app.services.lifecycle import transition
from app.services.routing import route_classification
from app.services.storage import get_storage
from contextlib import ExitStack


def locked_document(document_id: UUID, session: Session) -> Document:
    try:
        document = session.scalar(select(Document).where(Document.document_id == document_id).with_for_update(nowait=True))
    except OperationalError as exc:
        session.rollback()
        if getattr(exc.orig, 'sqlstate', None) == '55P03':
            raise DocumentError(409, 'DOCUMENT_ALREADY_PROCESSING') from None
        raise
    if document is None:
        raise DocumentError(404, 'DOCUMENT_NOT_FOUND')
    return document


def process_document(document_id: UUID, session: Session, settings: Settings,
                     provider: DocumentProvider) -> ProcessingResult:
    document = locked_document(document_id, session)
    if document.status == S.RECHAZADO:
        raise DocumentError(409, 'DOCUMENT_REJECTED')
    previous = ProcessingResult.model_validate(document.processing_result) if document.processing_result else None
    if previous and document.status in (S.ENRUTADO, S.ENTREGADO, S.EN_REVISION_HUMANA, S.RESUELTO):
        return previous
    if previous and document.status == S.EVALUADO and previous.validation and previous.validation.valid:
        previous.routing = route_classification(previous.classification)
        transition(document, S.ENRUTADO, 'LOCAL_DESTINATION_REGISTERED')
        previous.status = S.ENRUTADO
        document.processing_result = previous.model_dump(mode='json')
        session.commit()
        return previous
    state = {'document_id': str(document_id), 'format': document.format}
    if previous:
        for key in ('content', 'classification', 'extraction'):
            value = getattr(previous, key)
            if value is not None:
                state[key] = value
    if document.status == S.FALLO_TECNICO:
        resume = S.EXTRAIDO if state.get('extraction') else S.CLASIFICADO if state.get('classification') else S.VALIDADO
        transition(document, resume, 'RETRY_REQUESTED')
    document.processing_attempts += 1
    failure = None
    resources = ExitStack()
    try:
        state['path'] = resources.enter_context(get_storage(settings, document.storage_backend, document.storage_bucket).materialize(document.storage_key, settings.max_upload_bytes))
        for update in build_processing_graph(provider, settings).stream(state, stream_mode='updates'):
            for values in update.values():
                if not values:
                    continue
                state.update(values)
                for key, status in (('classification', S.CLASIFICADO), ('extraction', S.EXTRAIDO),
                                    ('validation', S.EVALUADO), ('routing', S.ENRUTADO)):
                    if key in values:
                        transition(document, status, f'{key.upper()}_COMPLETED')
        if state['validation'].requires_human_review:
            transition(document, S.EN_REVISION_HUMANA, 'DOCUMENTARY_VALIDATION_ISSUES')
    except (ProviderError, DocumentError, OSError) as exc:
        if isinstance(exc, OSError):
            exc = DocumentError(503, "DOCUMENT_STORAGE_UNAVAILABLE")
        failure = exc
        transition(document, S.FALLO_TECNICO, exc.code if isinstance(exc, ProviderError) else exc.detail)
        if document.processing_attempts >= settings.max_processing_attempts:
            transition(document, S.EN_REVISION_HUMANA, 'RETRIES_EXHAUSTED')
    finally:
        resources.close()
    result = ProcessingResult(
        document_id=document_id, status=document.status, processed_at=datetime.now(UTC), model=settings.gemini_model,
        **{key: state.get(key) for key in ('content', 'classification', 'extraction', 'validation', 'routing')},
        error_code=(failure.code if isinstance(failure, ProviderError) else failure.detail) if failure else None,
    )
    document.processing_result = result.model_dump(mode='json')
    session.commit()
    if failure:
        raise failure
    return result
