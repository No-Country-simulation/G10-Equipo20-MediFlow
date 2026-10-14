from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4
import smtplib

import pytest
from sqlalchemy import select, func

from app.core.auth import require_superadmin
from app.core.config import get_settings
from app.main import app
from app.models.destination import Destination
from app.models.document import Document
from app.models.notification import EmailNotification
from app.services.email_notifications import SMTPNotifier, process_email_notification, SMTPInput, save_smtp, smtp_configuration
from app.services.notifications import schedule_notification


def test_destination_email_recipients(client):
    body = {'code': 'TEST_EMAILS', 'name': 'Email destination', 'kind': 'QUEUE',
            'emails': 'Area@example.com, area@example.com, responsable@example.com'}
    assert client.post('/destinations', json=body).status_code == 201
    detail = client.get('/destinations/TEST_EMAILS').json()
    assert detail['emails'] == ['area@example.com', 'responsable@example.com']
    assert client.patch('/destinations/TEST_EMAILS', json={'emails': 'broken-address'}).status_code == 422
    assert client.patch('/destinations/TEST_EMAILS', json={'emails': [{}]}).status_code == 422
    assert client.patch('/destinations/TEST_EMAILS', json={'emails': ['a@example.com'] * 51}).status_code == 200
    assert client.patch('/destinations/TEST_EMAILS', json={'emails': [f'a{i}@example.com' for i in range(51)]}).status_code == 422
    assert client.patch('/destinations/TEST_EMAILS', json={'name': 'Renamed'}).status_code == 200
    assert client.get('/destinations/TEST_EMAILS').json()['emails'] == ['a@example.com']
    assert client.patch('/destinations/TEST_EMAILS', json={'emails': ''}).status_code == 200
    assert client.get('/destinations/TEST_EMAILS').json()['emails'] == []


def test_smtp_admin_settings_preserve_and_hide_password(client, session):
    app.dependency_overrides[require_superadmin] = lambda: {'id': 'test', 'role': 'SUPERADMIN'}
    response = client.get('/admin/smtp')
    assert response.status_code == 200 and not response.json()['enabled']
    assert response.headers['cache-control'] == 'no-store'
    body = {'enabled': False, 'host': 'smtp.example.com', 'port': 587, 'security': 'STARTTLS',
            'username': 'user', 'sender': 'sender@example.com', 'password': ' test-secret '}
    response = client.put('/admin/smtp', json=body)
    assert response.status_code == 200 and response.json()['password_configured']
    assert 'test-secret' not in response.text
    assert 'test-secret' not in client.get('/admin/smtp').text
    assert 'test-secret' not in client.get('/admin/configuration').text
    assert smtp_configuration(session)['password'] == ' test-secret '
    body.pop('password')
    body['enabled'] = True
    assert client.put('/admin/smtp', json=body).json()['enabled']
    response = client.put('/admin/smtp', json={**body, 'clear_password': True})
    assert response.status_code == 422
    assert 'test-secret' not in response.text
    assert client.get('/admin/smtp').json()['password_configured']
    body['enabled'] = False
    assert not client.put('/admin/smtp', json={**body, 'clear_password': True}).json()['password_configured']
    assert client.put('/admin/configuration/SMTP_ENABLED', json={'value': 'true'}).status_code == 409
    app.dependency_overrides.pop(require_superadmin)
    assert client.get('/admin/smtp').status_code == 401
    assert client.put('/admin/smtp', json=body).status_code == 401


@pytest.mark.parametrize('event', ['DELIVERED', 'REVIEW'])
def test_email_outbox_requires_explicit_activation_and_uses_current_recipients(session, event):
    destination = Destination(code='TEST_SMTP', name='SMTP test', kind='QUEUE', active=True,
                              slack_webhook_url='', emails=['old@example.com'])
    session.add(destination)
    if event == 'REVIEW':
        destination = session.get(Destination, 'REVISION_HUMANA')
        destination.emails = ['old@example.com']
    document = Document(document_id=uuid4(), original_filename='test.pdf', format='pdf', size_bytes=1,
        received_at=datetime.now(UTC), status='EN_REVISION_HUMANA' if event == 'REVIEW' else 'ENTREGADO',
        country='CO', processing_attempts=1, storage_backend='local')
    session.add(document)
    session.flush()
    result = SimpleNamespace(priority=None, routing=SimpleNamespace(destination=destination.code,
                             delivery_status='DELIVERED_LOCAL'), classification=None)
    settings = get_settings()
    transport = Mock()
    schedule_notification(session, document, result, settings)
    assert session.scalar(select(func.count()).select_from(EmailNotification)) == 0
    assert not process_email_notification(session, settings, transport)
    transport.send.assert_not_called()
    save_smtp(session, SMTPInput(enabled=True, host='smtp.example.com', username='user',
              password='secret', sender='sender@example.com'))
    schedule_notification(session, document, result, settings)
    schedule_notification(session, document, result, settings)
    session.flush()
    rows = session.scalars(select(EmailNotification)).all()
    assert len(rows) == 1 and rows[0].event == event
    destination.emails = ['current@example.com']
    assert process_email_notification(session, settings, transport)
    assert transport.send.call_args.args[1] == ['current@example.com']
    assert rows[0].status == 'SENT'
    assert not process_email_notification(session, settings, transport)


@pytest.mark.parametrize('security', ['STARTTLS', 'SSL_TLS'])
def test_smtp_transport_uses_tls_and_keeps_recipients_private(security):
    configuration = {'host': 'smtp.example.com', 'port': '587', 'security': security,
                     'username': 'user', 'password': ' secret ', 'sender': 'sender@example.com'}
    with patch('app.services.email_notifications.smtplib.SMTP') as plain, patch('app.services.email_notifications.smtplib.SMTP_SSL') as tls:
        client = (tls if security == 'SSL_TLS' else plain).return_value.__enter__.return_value
        client.send_message.return_value = {}
        SMTPNotifier().send(configuration, ['a@example.com', 'b@example.com'], {'subject': 'Test', 'body': 'Link'})
        client.login.assert_called_once_with('user', ' secret ')
        message = client.send_message.call_args.args[0]
        assert message['To'] == 'sender@example.com'
        assert client.send_message.call_args.kwargs['to_addrs'] == ['a@example.com', 'b@example.com']
        assert client.starttls.call_count == (1 if security == 'STARTTLS' else 0)


@pytest.mark.parametrize('failure,status', [(smtplib.SMTPAuthenticationError(535, b'private detail'), 'FAILED'),
    (smtplib.SMTPServerDisconnected('private detail'), 'UNKNOWN')])
def test_email_failure_and_disabled_queue(session, failure, status):
    settings = get_settings()
    save_smtp(session, SMTPInput(enabled=True, host='smtp.example.com', username='user',
              password='secret', sender='sender@example.com'))
    destination = Destination(code='TEST_SMTP_FAILURE', name='Failure test', kind='QUEUE', active=True,
                              slack_webhook_url='', emails=['test@example.com'])
    document = Document(document_id=uuid4(), original_filename='test.pdf', format='pdf', size_bytes=1,
        received_at=datetime.now(UTC), status='ENTREGADO', country='CO', storage_backend='local')
    session.add_all([destination, document]); session.flush()
    from app.services.email_notifications import schedule_email_notification
    schedule_email_notification(session, document, destination, 'DELIVERED', settings)
    session.flush()
    row = session.scalar(select(EmailNotification))
    transport = Mock()
    save_smtp(session, SMTPInput(enabled=False))
    assert not process_email_notification(session, settings, transport)
    transport.send.assert_not_called()
    save_smtp(session, SMTPInput(enabled=True, host='smtp.example.com', username='user', sender='sender@example.com'))
    transport.send.side_effect = failure
    assert process_email_notification(session, settings, transport)
    assert row.status == status and row.attempts == 1
    assert 'private detail' not in row.error_code
    row.retry_at = datetime.now(UTC) - timedelta(seconds=1)
    session.flush()
    transport.send.side_effect = None
    if status == 'FAILED':
        assert process_email_notification(session, settings, transport)
        assert row.status == 'SENT' and row.attempts == 2
    else:
        assert not process_email_notification(session, settings, transport)
