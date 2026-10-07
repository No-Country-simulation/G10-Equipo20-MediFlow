from datetime import UTC, datetime
from app.schemas.processing import ProcessingResult, ReviewRequest, ReviewAudit
from app.schemas.lifecycle import DocumentStatus as S
from app.services.processing import locked_document
from app.services.processing_validation import validate_processing
from app.services.lifecycle import transition
from app.services.routing import route_classification
from app.services.triage import detect_priority, calculate_quality, local_alert
from app.services.errors import DocumentError
from app.services.patients import assess_patient, link_patient


def review_document(document_id, request: ReviewRequest, session, settings) -> ProcessingResult:
    document = locked_document(document_id, session)
    from app.services.jobs import active_job
    if active_job(session, document_id):
        raise DocumentError(409, 'DOCUMENT_ALREADY_PROCESSING')
    from app.services.backups import schedule_backup
    from app.services.documentary_policy import load_policy, annotate_text_evidence, clinical_projection
    if document.status != S.EN_REVISION_HUMANA or not document.processing_result:
        raise DocumentError(409, 'DOCUMENT_NOT_AWAITING_REVIEW')
    previous = ProcessingResult.model_validate(document.processing_result)
    result = previous.model_copy(deep=True)
    corrections = {key: getattr(request, key) for key in ('content', 'classification', 'extraction') if getattr(request, key) is not None}
    if (request.action == 'APPROVE' and corrections) or (request.action == 'CORRECT' and not corrections):
        raise DocumentError(422, 'INVALID_REVIEW_ACTION')
    if not request.notes.strip() or not request.reviewer.strip():
        raise DocumentError(422, 'REVIEW_REASON_REQUIRED')
    if request.action == 'REJECT':
        if corrections:
            raise DocumentError(422, 'INVALID_REVIEW_ACTION')
        transition(document, S.RECHAZADO, 'HUMAN_REVIEW_REJECT')
        result.status, result.routing, result.processed_at = S.RECHAZADO, None, datetime.now(UTC)
        document.rejection_reason = request.notes.strip()[:255]
        document.processing_result = result.model_dump(mode='json')
        audit = ReviewAudit(action=request.action, reviewer=request.reviewer, notes=request.notes,
                            reviewed_at=result.processed_at, previous_result=previous)
        document.review_history = [*(document.review_history or []), audit.model_dump(mode='json')]
        schedule_backup(session, document, settings)
        session.commit()
        return result
    for key, value in corrections.items():
        setattr(result, key, value.model_copy(deep=True))
    if result.content is None or result.classification is None or result.extraction is None:
        raise DocumentError(422, 'REVIEW_REQUIRES_COMPLETE_RESULT')
    pages = result.content.pages
    expected_pages = [None] if document.format == 'text' else list(range(1, len(pages) + 1))
    if not pages or len(pages) > settings.processing_max_pages or [p.page for p in pages] != expected_pages:
        raise DocumentError(422, 'INVALID_REVIEW_PAGES')
    if (previous.content and len(pages) != len(previous.content.pages)) or (document.format != 'pdf' and len(pages) != 1):
        raise DocumentError(422, 'INVALID_REVIEW_PAGES')
    if sum(len(p.text) for p in pages) > settings.processing_max_characters:
        raise DocumentError(422, 'PROCESSING_TEXT_LIMIT')
    for page in pages:
        page.uncertain = '[ILEGIBLE]' in page.text.upper()
        if request.content is not None:
            page.method, page.engine = 'human_corrected', None
    if document.format == 'text':
        result.classification.evidence = annotate_text_evidence(result.content, result.classification.evidence)
        for field in result.extraction.fields:
            field.evidence = annotate_text_evidence(result.content, field.evidence)
    policy = previous.quality.policy if previous.quality else None
    if policy is None or policy.get('document_type') != result.classification.document_type:
        policy = load_policy(session, result.classification.document_type, settings.min_document_quality)
    result.validation = validate_processing(result.content, result.classification, result.extraction, policy)
    result.priority = detect_priority(result.content)
    if result.priority.ambiguous:
        result.validation.issues.append('PRIORITY_AMBIGUOUS')
        result.validation.valid = False
        result.validation.requires_human_review = True
    result.quality = calculate_quality(result.content, result.classification, result.extraction,
                                       result.validation, settings.min_document_quality, policy)
    if result.quality.score < result.quality.threshold:
        result.validation.issues.append('LOW_DOCUMENT_QUALITY')
        result.validation.valid = False
        result.validation.requires_human_review = True
    result.local_alert = local_alert(result.priority)
    result.patient = assess_patient(result.extraction, document.country, result.validation, session)
    if not result.validation.valid:
        raise DocumentError(422, 'REVIEW_HAS_UNRESOLVED_ISSUES:' + ','.join(result.validation.issues))
    result.routing = route_classification(result.classification, result.priority, session)
    result.pipeline_version = 'documentary-v6'
    result.clinical_data = clinical_projection(result.extraction)
    transition(document, S.RESUELTO, 'HUMAN_REVIEW_' + request.action)
    transition(document, S.ENRUTADO, 'LOCAL_DESTINATION_REGISTERED')
    result.patient = link_patient(document, result.extraction, result.patient, session)
    transition(document, S.ENTREGADO, 'LOCAL_INBOX_DELIVERED')
    result.routing.delivery_status = 'DELIVERED_LOCAL'
    result.status, result.error_code, result.processed_at = S.ENTREGADO, None, datetime.now(UTC)
    document.processing_result = result.model_dump(mode='json')
    audit = ReviewAudit(action=request.action, reviewer=request.reviewer, notes=request.notes,
                        reviewed_at=result.processed_at, previous_result=previous)
    document.review_history = [*(document.review_history or []), audit.model_dump(mode='json')]
    schedule_backup(session, document, settings)
    session.commit()
    return result
