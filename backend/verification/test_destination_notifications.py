from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select, func

from app.core.auth import require_staff
from app.core.config import get_settings
from app.main import app
from app.models.destination import Destination
from app.models.document import Document
from app.models.notification import SlackNotification
from app.services.notifications import schedule_notification, process_notification, SlackNotifier, SlackError
from app.schemas.processing import PriorityResult, RoutingResult

WEBHOOK = 'https://hooks.slack.com/services/TEST/CHANNEL/FAKE'


def test_contact_api_persistence_validation_and_secret_permissions(client):
    created = client.post('/destinations', json={'code': 'TEST_CONTACTS', 'name': 'Test destination', 'kind': 'QUEUE'})
    assert created.status_code == 201, created.text
    assert 'emails' not in created.json()
    assert not created.json()['slack_configured']
    saved = client.patch('/destinations/TEST_CONTACTS', json={'slack_webhook_url': WEBHOOK})
    assert saved.status_code == 200, saved.text
    assert saved.json()['slack_configured']
    assert 'slack_webhook_url' not in saved.json()
    detail = client.get('/destinations/TEST_CONTACTS')
    assert detail.json()['slack_webhook_url'] == WEBHOOK
    assert detail.headers['cache-control'] == 'no-store'
    assert WEBHOOK not in client.get('/destinations').text
    assert client.get('/routing-rules').status_code == 200
    assert client.patch('/destinations/TEST_CONTACTS', json={'emails': ['invalid-email']}).status_code == 422
    assert client.patch('/destinations/TEST_CONTACTS', json={'slack_webhook_url': 'https://example.com/services/A/B/C'}).status_code == 422
    assert client.patch('/destinations/TEST_CONTACTS', json={'name': 'Renamed'}).status_code == 200
    assert client.get('/destinations/TEST_CONTACTS').json()['slack_webhook_url'] == WEBHOOK
    app.dependency_overrides[require_staff] = lambda: {'id': 'test', 'role': 'EMPLOYEE', 'permissions': ['DESTINATIONS_READ']}
    assert client.get('/destinations').status_code == 200
    assert client.get('/destinations/TEST_CONTACTS').status_code == 403
    assert client.patch('/destinations/TEST_CONTACTS', json={'slack_webhook_url': ''}).status_code == 403
    app.dependency_overrides[require_staff] = lambda: {'id': 'test', 'role': 'SUPERADMIN'}
    cleared = client.patch('/destinations/TEST_CONTACTS', json={'slack_webhook_url': ''})
    assert cleared.status_code == 200
    assert not cleared.json()['slack_configured']
    assert 'emails' not in cleared.json()


@pytest.mark.parametrize('level', ['ROUTINE', 'URGENT'])
def test_outbox_only_after_delivery_and_deduplicates(session, level):
    settings = get_settings()
    session.add(Destination(code='TEST_DELIVERY', name='Delivery test', kind='QUEUE', active=True,
                            slack_webhook_url=WEBHOOK))
    doc = Document(document_id=uuid4(), original_filename='test.txt', format='text', size_bytes=1,
        received_at=datetime.now(UTC), status='ENRUTADO', country='CO', processing_attempts=1,
        storage_backend='local', patient_match_status='NOT_EVALUATED')
    session.add(doc); session.flush()
    result = SimpleNamespace(priority=PriorityResult(level=level, source='DEFAULT'),
        routing=RoutingResult(destination='TEST_DELIVERY', routed_at=datetime.now(UTC)), classification=None)
    schedule_notification(session, doc, result, settings)
    assert session.scalar(select(func.count()).select_from(SlackNotification)) == 0
    doc.status = 'ENTREGADO'
    result.routing.delivery_status = 'DELIVERED_LOCAL'
    schedule_notification(session, doc, result, settings)
    schedule_notification(session, doc, result, settings)
    session.flush()
    rows = session.scalars(select(SlackNotification)).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.destination_code == 'TEST_DELIVERY'
    transport = Mock()
    transport.send.side_effect = SlackError('SLACK_RATE_LIMITED', retryable=True, retry_after=60)
    assert process_notification(session, settings, transport)
    assert row.status == 'FAILED' and row.retryable
    row.retry_at = datetime.now(UTC) - timedelta(seconds=1)
    session.flush()
    transport.send.side_effect = None
    assert process_notification(session, settings, transport)
    transport.send.assert_called_with('DELIVERED', row.payload, webhook=WEBHOOK)
    assert row.status == 'SENT' and row.attempts == 2
    assert not process_notification(session, settings, transport)


def test_slack_transport_uses_destination_webhook():
    notifier = SlackNotifier(get_settings())
    with patch('app.services.notifications.httpx.Client') as client:
        client.return_value.__enter__.return_value.post.return_value = SimpleNamespace(status_code=200, text='ok')
        notifier.send('DELIVERED', {'text': 'Test'}, webhook=WEBHOOK)
        client.return_value.__enter__.return_value.post.assert_called_once_with(WEBHOOK, json={'text': 'Test'})
    with pytest.raises(SlackError) as error:
        notifier.send('DELIVERED', {}, webhook='')
    assert error.value.code == 'SLACK_NOT_CONFIGURED'


def test_database_routing_contract(session):
    from app.schemas.processing import ClassificationResult
    from app.services.routing import route_classification
    classification = ClassificationResult(document_type='PRESCRIPTION', specialty='CARDIOLOGY', evidence=None, reason='test')
    route = route_classification(classification, session=session)
    assert route.destination == 'FARMACIA_HOSPITALARIA'


def test_review_is_listed_and_notified_without_clinical_routing(client, session):
    from app.schemas.processing import ValidationResult
    destination = session.get(Destination, 'REVISION_HUMANA')
    destination.slack_webhook_url = WEBHOOK
    document = Document(document_id=uuid4(), original_filename='revision.pdf', format='pdf', size_bytes=1,
        received_at=datetime.now(UTC), status='EN_REVISION_HUMANA', country='CO', processing_attempts=1,
        storage_backend='local', patient_match_status='NOT_EVALUATED', processing_result={'routing': None})
    session.add(document); session.flush()
    result = SimpleNamespace(priority=PriorityResult(level='ROUTINE', source='DEFAULT'),
        routing=None, classification=None,
        validation=ValidationResult(valid=False, requires_human_review=True,
            issues=['MISSING_REQUIRED_FIELD:medication_frequency']))
    schedule_notification(session, document, result, get_settings())
    schedule_notification(session, document, result, get_settings())
    session.flush()
    rows = session.scalars(select(SlackNotification).where(SlackNotification.document_id == document.document_id)).all()
    assert len(rows) == 1
    assert rows[0].level == 'REVIEW'
    assert rows[0].destination_code == 'REVISION_HUMANA'
    response = client.get('/documents?destination=REVISION_HUMANA&country=CO')
    assert response.status_code == 200, response.text
    assert str(document.document_id) in {item['document_id'] for item in response.json()['items']}
    assert document.processing_result['routing'] is None


def test_critical_alert_uses_urgent_channel():
    settings = get_settings().model_copy(update={})
    from pydantic import SecretStr
    settings.slack_webhook_url = SecretStr('https://hooks.slack.com/services/GENERAL/TEST/TEST')
    settings.slack_webhook_url_urgente = SecretStr(WEBHOOK)
    with patch('app.services.notifications.httpx.Client') as client:
        client.return_value.__enter__.return_value.post.return_value = SimpleNamespace(status_code=200, text='ok')
        SlackNotifier(settings).send('CRITICAL', {'text': 'Test'})
        client.return_value.__enter__.return_value.post.assert_called_once_with(WEBHOOK, json={'text': 'Test'})


@pytest.mark.parametrize('event', ['URGENT', 'DELIVERED', 'REVIEW'])
def test_designed_slack_notice_preserves_filename_and_explicit_channel_mention(event):
    from app.schemas.processing import ClassificationResult, ValidationResult
    from app.services.slack_message import notification_payload
    filename = 'Fórmula médica & informe <!everyone>.pdf'
    document = SimpleNamespace(document_id=uuid4(), original_filename=filename, country='CO')
    result = SimpleNamespace(priority=PriorityResult(level='URGENT' if event == 'URGENT' else 'ROUTINE', source='DEFAULT'),
        classification=ClassificationResult(document_type='PRESCRIPTION', specialty='GENERAL_MEDICINE', evidence=None, reason='test'),
        validation=ValidationResult(valid=False, requires_human_review=True,
            issues=['MISSING_REQUIRED_FIELD:medication_frequency', 'INCOMPLETE_ENTITY:medication-1']))
    payload = notification_payload(document, result, get_settings(), event=event, destination_name='Bandeja de prueba')
    assert payload['text'].count('<!channel>') == 1
    assert '<!everyone>' not in payload['text']
    assert '&lt;!everyone&gt;' in payload['text']
    assert payload['blocks'][0]['type'] == 'header'
    filename_block = payload['blocks'][2]['text']
    assert filename_block['type'] == 'plain_text' and filename in filename_block['text']
    assert payload['blocks'][1]['text']['text'].startswith('<!channel>')
    assert payload['blocks'][-1]['elements'][0]['url'].endswith('/documents/' + str(document.document_id))
    assert not payload['unfurl_links'] and not payload['unfurl_media']
    if event == 'REVIEW':
        assert 'Falta frecuencia de administración.' in payload['text']
        assert 'MISSING_REQUIRED_FIELD' not in payload['text']
    if event == 'URGENT':
        assert 'procesamiento en curso' in payload['text']
