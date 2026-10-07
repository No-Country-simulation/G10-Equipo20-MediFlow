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
from app.services.storage import get_storage
from app.services.patients import link_patient


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
                     provider: DocumentProvider, *, job_id=None, token=None) -> ProcessingResult:
    from app.services.jobs import enqueue, owned_job, CountedProvider
    from app.services.backups import schedule_backup
    from app.services.documentary_policy import clinical_projection
    document = locked_document(document_id, session)
    previous = ProcessingResult.model_validate(document.processing_result) if document.processing_result else None
    if document.status == S.RECHAZADO:
        raise DocumentError(409, 'DOCUMENT_REJECTED')
    if previous and document.status == S.ENRUTADO and job_id and previous.routing:
        owned_job(session, job_id, token)
        previous.patient = link_patient(document, previous.extraction, previous.patient, session)
        transition(document, S.ENTREGADO, 'LOCAL_INBOX_DELIVERED')
        previous.routing.delivery_status = 'DELIVERED_LOCAL'
        previous.status = S.ENTREGADO
        document.processing_result = previous.model_dump(mode='json')
        schedule_backup(session, document, settings)
    if previous and document.status in (S.ENRUTADO, S.ENTREGADO, S.EN_REVISION_HUMANA, S.RESUELTO):
        if job_id:
            job = owned_job(session, job_id, token)
            job.status, job.active_node = 'SUCCEEDED', None
        session.commit()
        return previous
    if job_id is None:
        job = enqueue(session, document_id, running=True)
        job_id, token = job.id, job.token
    job = owned_job(session, job_id, token)
    document = locked_document(document_id, session)
    if document.processing_attempts >= settings.max_processing_attempts:
        if document.status == S.FALLO_TECNICO:
            transition(document, S.EN_REVISION_HUMANA, 'RETRIES_EXHAUSTED')
        else:
            transition(document, S.FALLO_TECNICO, 'INTERRUPTED_EXECUTION')
            transition(document, S.EN_REVISION_HUMANA, 'RETRIES_EXHAUSTED')
        if document.processing_result:
            document.processing_result = {**document.processing_result, 'status': document.status}
            schedule_backup(session, document, settings)
        job.status, job.error_code = 'FAILED', 'RETRIES_EXHAUSTED'
        session.commit()
        raise DocumentError(409, 'RETRIES_EXHAUSTED')
    if document.status == S.FALLO_TECNICO:
        resume = S.EXTRAIDO if previous and previous.extraction else S.CLASIFICADO if previous and previous.classification else S.VALIDADO
        transition(document, resume, 'RETRY_REQUESTED')
    document.processing_attempts += 1
    job.attempt = document.processing_attempts
    session.commit()
    state = {'document_id': str(document_id), 'format': document.format, 'country': document.country}
    if previous:
        for key in ('content', 'classification', 'extraction'):
            value = getattr(previous, key)
            if value is not None:
                state[key] = value
    if job.policy_snapshot:
        state['policy'] = job.policy_snapshot
    failure = None
    def before_node(name):
        current = owned_job(session, job_id, token)
        current.active_node = name
        session.commit()
    def before_call(name):
        current = owned_job(session, job_id, token)
        calls = dict(current.provider_calls or {})
        calls[name] = calls.get(name, 0) + 1
        current.provider_calls = calls
        session.commit()
    measured = CountedProvider(provider, before_call)
    def result_snapshot():
        return ProcessingResult(document_id=document_id, status=document.status, processed_at=datetime.now(UTC),
            model=getattr(provider, 'model', settings.gemini_model), provider=getattr(provider, 'name', 'gemini'),
            pipeline_version='documentary-v6',
            **{key: state.get(key) for key in ('content', 'classification', 'extraction', 'validation', 'priority',
                                             'quality', 'local_alert', 'routing', 'patient')},
            clinical_data=clinical_projection(state.get('extraction')),
            error_code=(failure.code if isinstance(failure, ProviderError) else failure.detail) if failure else None)
    try:
        before_node('ingest')
        with get_storage(settings, document.storage_backend, document.storage_bucket).materialize(document.storage_key, settings.max_upload_bytes) as path:
            if document.sha256:
                import hashlib
                if hashlib.sha256(path.read_bytes()).hexdigest() != document.sha256:
                    raise DocumentError(422, 'ORIGINAL_INTEGRITY_MISMATCH')
            state['path'] = path
            for update in build_processing_graph(measured, settings, session, before_node).stream(state, stream_mode='updates'):
                for name, values in update.items():
                    current = owned_job(session, job_id, token)
                    document = locked_document(document_id, session)
                    if values:
                        state.update(values)
                        for key, status in (('classification', S.CLASIFICADO), ('extraction', S.EXTRAIDO),
                                            ('validation', S.EVALUADO), ('routing', S.ENRUTADO)):
                            if key in values:
                                transition(document, status, f'{key.upper()}_COMPLETED')
                    if name not in current.completed_nodes:
                        current.completed_nodes = [*current.completed_nodes, name]
                    current.policy_snapshot = state.get('policy')
                    document.processing_result = result_snapshot().model_dump(mode='json')
                    session.commit()
        owned_job(session, job_id, token)
        document = locked_document(document_id, session)
        if state['validation'].requires_human_review:
            transition(document, S.EN_REVISION_HUMANA, 'DOCUMENTARY_VALIDATION_ISSUES')
        elif state.get('routing'):
            state['patient'] = link_patient(document, state.get('extraction'), state['patient'], session)
            transition(document, S.ENTREGADO, 'LOCAL_INBOX_DELIVERED')
            state['routing'].delivery_status = 'DELIVERED_LOCAL'
    except Exception as exc:
        if isinstance(exc, DocumentError) and exc.detail == 'PROCESSING_LEASE_LOST':
            raise
        session.rollback()
        owned_job(session, job_id, token)
        document = locked_document(document_id, session)
        failure = (exc if isinstance(exc, (ProviderError, DocumentError)) else
                   DocumentError(503, 'DOCUMENT_STORAGE_UNAVAILABLE' if isinstance(exc, OSError) else 'PROCESSING_INTERNAL_ERROR'))
        transition(document, S.FALLO_TECNICO, failure.code if isinstance(failure, ProviderError) else failure.detail)
        if document.processing_attempts >= settings.max_processing_attempts:
            transition(document, S.EN_REVISION_HUMANA, 'RETRIES_EXHAUSTED')
    job = owned_job(session, job_id, token)
    result = result_snapshot()
    document.processing_result = result.model_dump(mode='json')
    if result.patient and document.patient_id is None:
        document.patient_match_status, document.patient_match_reason = result.patient.status, result.patient.reason
    job.status, job.active_node = ('FAILED' if failure else 'SUCCEEDED'), None
    job.error_code, job.lease_until = result.error_code, None
    schedule_backup(session, document, settings)
    session.commit()
    if failure:
        raise failure
    return result
