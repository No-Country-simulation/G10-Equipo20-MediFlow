from datetime import UTC, datetime
from app.schemas.processing import ProcessingResult, ReviewRequest, ReviewAudit
from app.schemas.lifecycle import DocumentStatus as S
from app.services.processing import locked_document
from app.services.processing_validation import validate_processing
from app.services.lifecycle import transition
from app.services.routing import route_classification
from app.services.errors import DocumentError


def review_document(document_id, request: ReviewRequest, session, settings) -> ProcessingResult:
    document = locked_document(document_id, session)
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
        session.commit()
        return result
    for key, value in corrections.items():
        setattr(result, key, value.model_copy(deep=True))
    if result.content is None or result.classification is None or result.extraction is None:
        raise DocumentError(422, 'REVIEW_REQUIRES_COMPLETE_RESULT')
    pages = result.content.pages
    if not pages or len(pages) > settings.processing_max_pages or [p.page for p in pages] != list(range(1, len(pages) + 1)):
        raise DocumentError(422, 'INVALID_REVIEW_PAGES')
    if (previous.content and len(pages) != len(previous.content.pages)) or (document.format != 'pdf' and len(pages) != 1):
        raise DocumentError(422, 'INVALID_REVIEW_PAGES')
    if sum(len(p.text) for p in pages) > settings.processing_max_characters:
        raise DocumentError(422, 'PROCESSING_TEXT_LIMIT')
    for page in pages:
        page.uncertain = '[ILEGIBLE]' in page.text.upper()
        if request.content is not None:
            page.method, page.engine = 'human_corrected', None
    result.validation = validate_processing(result.content, result.classification, result.extraction)
    if not result.validation.valid:
        raise DocumentError(422, 'REVIEW_HAS_UNRESOLVED_ISSUES:' + ','.join(result.validation.issues))
    result.routing = route_classification(result.classification)
    transition(document, S.RESUELTO, 'HUMAN_REVIEW_' + request.action)
    transition(document, S.ENRUTADO, 'LOCAL_DESTINATION_REGISTERED')
    result.status, result.error_code, result.processed_at = S.ENRUTADO, None, datetime.now(UTC)
    document.processing_result = result.model_dump(mode='json')
    audit = ReviewAudit(action=request.action, reviewer=request.reviewer, notes=request.notes,
                        reviewed_at=result.processed_at, previous_result=previous)
    document.review_history = [*(document.review_history or []), audit.model_dump(mode='json')]
    session.commit()
    return result
