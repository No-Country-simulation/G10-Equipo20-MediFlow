import asyncio
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient

from app.core.auth import require_staff
from app.core.config import Settings
from app.core.request_limits import RequestBodyLimitMiddleware
from app.main import app
from app.models.document import Document
from app.providers.base import ProviderError
from app.repositories.documents import DocumentRepository
from app.schemas.lifecycle import DocumentStatus
from app.schemas.processing import (
    ClassificationResult, ContentPage, ContentResult, Evidence, ExtractedField,
    ExtractionResult, PriorityResult, ProcessingResult,
)
from app.services.documents import DocumentService
from app.services.errors import DocumentError
from app.services.processing import process_document
from app.services.storage import LocalDocumentStorage


@pytest.mark.parametrize('declared', [None, b'1', b'999999999'])
def test_request_limit_stops_receiving_before_parser(declared):
    received, sent = [], []
    downstream = Mock()
    settings = Settings(postgres_password='test', max_upload_bytes=1)

    async def receive():
        received.append(True)
        assert len(received) <= 2, 'Oversized body must not be fully consumed'
        return {'type': 'http.request', 'body': b'x' * (1024 * 1024), 'more_body': True}

    async def send(message):
        sent.append(message)

    scope = {'type': 'http', 'method': 'POST', 'headers':
             [] if declared is None else [(b'content-length', declared)]}
    with patch('app.core.request_limits.get_settings', return_value=settings):
        asyncio.run(RequestBodyLimitMiddleware(downstream)(scope, receive, send))
    downstream.assert_not_called()
    assert sent[0]['status'] == 413
    assert len(received) == (0 if declared == b'999999999' else 2)


@pytest.mark.parametrize('size', [0, 2 * 1024 * 1024, 10 * 1024 * 1024])
def test_bounded_multipart_replay_preserves_file(size):
    test_app = FastAPI()
    test_app.add_middleware(RequestBodyLimitMiddleware)

    @test_app.post('/')
    async def upload(file: UploadFile):
        return {'size': len(await file.read())}

    settings = Settings(postgres_password='test')
    with patch('app.core.request_limits.get_settings', return_value=settings), TestClient(test_app) as client:
        response = client.post('/', files={'file': ('test.pdf', b'x' * size, 'application/pdf')})
    assert response.status_code == 200, response.text
    assert response.json()['size'] == size


def test_oversized_file_never_reaches_original_storage(tmp_path):
    repository, storage = Mock(), LocalDocumentStorage(tmp_path / 'originals')
    source = BytesIO(b'x' * 200000)
    with pytest.raises(DocumentError) as error:
        DocumentService(repository, storage, 100000).ingest('test.pdf', source)
    assert error.value.status_code == 413
    assert source.tell() < 200000
    document = repository.add.call_args.args[0]
    assert document.status == 'RECHAZADO'
    assert document.storage_key is None
    assert not storage.directory.exists()


def review_source(document_id):
    text = 'Receta\nPaciente: Persona de Prueba\nMedicamento 5 mg cada 24 horas'
    def field(name, value):
        return ExtractedField(name=name, value=value, unit=None, evidence=Evidence(quote=value))
    return ProcessingResult(document_id=document_id, status='EN_REVISION_HUMANA',
        processed_at=datetime.now(UTC), model='test',
        content=ContentResult(pages=[ContentPage(text=text, method='submitted_text')]),
        classification=ClassificationResult(document_type='PRESCRIPTION', specialty='CARDIOLOGY',
            evidence=Evidence(quote='Receta'), reason='literal'),
        extraction=ExtractionResult(fields=[field('patient_name', 'Persona de Prueba'),
            field('medication_name', 'Medicamento'), field('medication_dose', '5 mg'),
            field('medication_frequency', 'cada 24 horas')]))


@pytest.mark.parametrize('action', ['APPROVE', 'CORRECT', 'REJECT'])
def test_review_audits_authenticated_actor_and_delivery(client, session, action):
    document_id = uuid4()
    result = review_source(document_id)
    document = Document(document_id=document_id, original_filename='test.json', format='text', size_bytes=1,
        received_at=datetime.now(UTC), status='EN_REVISION_HUMANA', country='CO', processing_attempts=1,
        storage_backend='local', processing_result=result.model_dump(mode='json'))
    session.add(document)
    session.flush()
    app.dependency_overrides[require_staff] = lambda: {
        'id': 'authenticated-reviewer', 'role': 'EMPLOYEE', 'permissions': ['DOCUMENTS_REVIEW', 'DOCUMENTS_READ']}
    body = {'action': action, 'reviewer': 'forged-administrator', 'notes': 'Original verificado',
            'confirmed_source_review': True}
    if action == 'CORRECT':
        body['extraction'] = result.extraction.model_dump(mode='json')
    response = client.post(f'/documents/{document_id}/review', json=body)
    assert response.status_code == 200, response.text
    audit = client.get(f'/documents/{document_id}/reviews').json()[0]
    assert audit['actor_id'] == audit['reviewer'] == 'authenticated-reviewer'
    assert audit['action'] == action and audit['reviewed_at']
    history = client.get(f'/documents/{document_id}/history').json()
    assert history and all(event['actor_id'] == 'authenticated-reviewer' for event in history)
    assert history[-1]['status'] == ('RECHAZADO' if action == 'REJECT' else 'ENTREGADO')


def test_read_permission_cannot_submit_review(client):
    app.dependency_overrides[require_staff] = lambda: {
        'id': 'reader', 'role': 'EMPLOYEE', 'permissions': ['DOCUMENTS_READ']}
    response = client.post(f'/documents/{uuid4()}/review', json={
        'action': 'REJECT', 'notes': 'Intento sin permiso', 'confirmed_source_review': True})
    assert response.status_code == 403


@pytest.mark.parametrize('text,expected', [
    ('Epicrisis: tromboembolismo pulmonar', None),
    ('Prioridad: crítica', 'CRITICAL'),
    ('Prioridad: urgente', 'URGENT'),
    ('Prioridad: rutina', 'ROUTINE'),
])
def test_provider_failure_does_not_invent_routine_priority(session, tmp_path, text, expected):
    settings = Settings(postgres_password='test', storage_backend='local', documents_dir=tmp_path,
                        max_processing_attempts=1)
    document = DocumentService(DocumentRepository(session), LocalDocumentStorage(tmp_path), settings.max_upload_bytes,
                               'CO').ingest_text(text, 'MANUAL')
    row = session.get(Document, document.document_id)
    provider = Mock()
    provider.model, provider.name = 'test', 'test'
    provider.classify.side_effect = ProviderError('TEST_PROVIDER_FAILURE')
    with pytest.raises(ProviderError):
        process_document(row.document_id, session, settings, provider)
    session.refresh(row)
    assert row.status == 'EN_REVISION_HUMANA'
    assert row.processing_result['error_code'] == 'TEST_PROVIDER_FAILURE'
    priority = row.processing_result['priority']
    assert (priority['level'] if priority else None) == expected
    assert row.processing_result['classification'] is None
    assert row.processing_result['extraction'] is None
    provider.classify.assert_called_once()
    provider.extract.assert_not_called()


def test_legacy_review_audit_remains_readable():
    from app.schemas.processing import ReviewAudit
    audit = ReviewAudit(action='REJECT', reviewer='legacy', notes='old record',
                        reviewed_at=datetime.now(UTC), previous_result=review_source(uuid4()))
    assert audit.actor_id is None


def test_exhausted_legacy_failure_clears_default_priority(session):
    document_id = uuid4()
    result = review_source(document_id)
    result.status = DocumentStatus.FALLO_TECNICO
    result.priority = PriorityResult(level='ROUTINE', source='DEFAULT')
    document = Document(document_id=document_id, original_filename='test.json', format='text', size_bytes=1,
        received_at=datetime.now(UTC), status='FALLO_TECNICO', country='CO', processing_attempts=3,
        storage_backend='local', processing_result=result.model_dump(mode='json'))
    session.add(document)
    session.flush()
    with pytest.raises(DocumentError, match='RETRIES_EXHAUSTED'):
        process_document(document_id, session, Settings(postgres_password='test'), Mock())
    session.refresh(document)
    assert document.status == 'EN_REVISION_HUMANA'
    assert document.processing_result['status'] == 'EN_REVISION_HUMANA'
    assert document.processing_result['priority'] is None
