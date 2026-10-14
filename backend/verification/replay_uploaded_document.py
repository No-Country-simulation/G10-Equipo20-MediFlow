"""Replay a stored result without LLM calls; optionally repair a delivered ID.

Run inside the API container with PYTHONPATH=/app. Default is read-only.
The original R2 object and all previous review snapshots remain intact.
"""
import argparse
from datetime import UTC, datetime
import hashlib
import json
from uuid import UUID

from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import get_engine
from app.graph.processing import build_processing_graph
from app.schemas.processing import ProcessingResult, ReviewAudit
from app.services.backups import schedule_backup
from app.services.content import ContentReader
from app.services.documentary_policy import clinical_projection
from app.services.identity_detection import complete_identity
from app.services.jobs import active_job
from app.services.patients import assess_patient, link_patient
from app.services.processing import locked_document
from app.services.processing_validation import validate_processing, describe_validation
from app.services.storage import get_storage


class CachedOnlyProvider:
    def __getattr__(self, name):
        raise RuntimeError(f'Unexpected provider call: {name}')


def replay(document_id, apply=False):
    settings = get_settings()
    with Session(get_engine(), expire_on_commit=False) as session:
        document = locked_document(document_id, session)
        if active_job(session, document_id):
            raise RuntimeError('Document has an active job')
        current = ProcessingResult.model_validate(document.processing_result)
        historical = (ProcessingResult.model_validate(document.review_history[0]['previous_result'])
                      if document.review_history else current)
        if not all((historical.content, historical.classification, historical.extraction)):
            raise RuntimeError('A complete stored result is required')
        provider = CachedOnlyProvider()
        with get_storage(settings, document.storage_backend, document.storage_bucket).materialize(
                document.storage_key, settings.max_upload_bytes) as path:
            integrity = bool(document.sha256) and hashlib.sha256(path.read_bytes()).hexdigest() == document.sha256
            if not integrity:
                raise RuntimeError('Original integrity check failed')
            fresh = ContentReader(provider, settings).read(path, document.format)
            if [(p.page, p.text) for p in fresh.pages] != [(p.page, p.text) for p in historical.content.pages]:
                raise RuntimeError('Stored text differs from the original')
            state = build_processing_graph(provider, settings, session).invoke({
                'document_id': str(document_id), 'path': path, 'format': document.format, 'country': document.country,
                'content': historical.content, 'classification': historical.classification,
                'extraction': historical.extraction,
                **({'policy': historical.quality.policy} if historical.quality and historical.quality.policy else {})})
        summary = {'document_id': str(document_id), 'original_sha256_verified': integrity,
            'text_matches_original': True, 'before_issues': historical.validation.issues,
            'after_issues': state['validation'].issues, 'quality': state['quality'].score,
            'patient_identity': state['patient'].identity_number,
            'priority': state['priority'].level, 'priority_ambiguous': state['priority'].ambiguous,
            'destination': state.get('routing').destination if state.get('routing') else None,
            'applied': False}
        if apply:
            if document.status != 'ENTREGADO' or not state['validation'].valid:
                raise RuntimeError('Repair requires a delivered document and a valid replay')
            extraction = complete_identity(current.content, current.extraction, document.country)
            if extraction == current.extraction:
                summary['repair'] = 'No missing identity to complete'
            else:
                updated = current.model_copy(deep=True)
                updated.extraction = extraction
                updated.validation = validate_processing(current.content, current.classification, extraction,
                    current.quality.policy if current.quality else None, document.country)
                updated.patient = assess_patient(extraction, document.country, updated.validation, session)
                if not updated.validation.valid or updated.patient.status != 'VALID_CANDIDATE':
                    raise RuntimeError('Repair requires verified, unambiguous patient evidence')
                updated.validation = describe_validation(updated.validation, extraction)
                updated.patient = link_patient(document, extraction, updated.patient, session)
                updated.clinical_data = clinical_projection(extraction)
                updated.pipeline_version = 'documentary-v11'
                updated.processed_at = datetime.now(UTC)
                document.processing_result = updated.model_dump(mode='json')
                audit = ReviewAudit(action='CORRECT', reviewer='system:documentary-v11',
                    notes='Reevaluación solicitada: identificación recuperada del texto original mediante contexto de paciente, excluyendo la firma del profesional. Original verificado por SHA-256; se conserva la entrega y el historial previo.',
                    reviewed_at=updated.processed_at, previous_result=current)
                document.review_history = [*(document.review_history or []), audit.model_dump(mode='json')]
                schedule_backup(session, document, settings)
                session.commit()
                summary['applied'] = True
                summary['patient_status'] = updated.patient.status
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document_id', type=UUID)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    replay(args.document_id, args.apply)
