"""Verify public TLS, proxy headers, secure login and optionally send a corrected Slack link.

Run explicitly in the API environment. --notify-document sends a real Slack
correction through the outbox, deduplicated per document as LINK_FIX.
"""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import secrets
import time
from uuid import UUID, uuid4

import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.auth import password_hash
from app.core.config import get_settings
from app.core.database import get_engine
from app.models.account import Account, LoginSession
from app.models.destination import Destination
from app.models.document import Document
from app.models.notification import SlackNotification
from app.schemas.processing import ProcessingResult
from app.services.slack_message import notification_payload


def run(report_path, document_id=None):
    settings = get_settings()
    base = settings.public_frontend_url
    assert base.startswith('https://'), 'Public URL must use HTTPS'
    report = {'public_url': base}
    password = secrets.token_urlsafe(32)
    # A temporary account exercises the real login route without changing any
    # existing account/password. Both account and sessions are removed below.
    with Session(get_engine()) as db:
        account = Account(email=f'https-check-{uuid4()}@example.com',
            password_hash=password_hash(password), role='EMPLOYEE', active=True,
            created_at=datetime.now(UTC))
        db.add(account)
        db.commit()
        try:
            with httpx.Client(base_url=base, timeout=20) as client:
                response = client.get('/')
                assert response.status_code == 200, response.status_code
                report['tls_and_home_verified'] = True
                redirect = client.get(base.replace('https://', 'http://', 1) + '/documents/test?view=1')
                assert redirect.status_code == 301
                assert redirect.headers['location'] == base + '/documents/test?view=1'
                report['http_redirect_verified'] = True
                credentials = {'email': account.email, 'password': password}
                rejected = client.post('/api/auth/admin-login', json=credentials,
                    headers={'Origin': 'https://untrusted.example.com'})
                assert rejected.status_code == 403
                response = client.post('/api/auth/admin-login', json=credentials, headers={'Origin': base})
                assert response.status_code == 200, (response.status_code, response.text)
                cookie = response.headers['set-cookie'].lower()
                assert '; secure' in cookie and '; httponly' in cookie and 'samesite=lax' in cookie
                report['https_origin_and_secure_cookie_verified'] = True
                assert client.get('/api/auth/me').status_code == 200
                assert client.post('/api/auth/logout', headers={'Origin': base}).status_code == 200
                assert client.get('/api/auth/me').status_code == 401
                report['login_and_logout_verified'] = True
        finally:
            db.execute(delete(LoginSession).where(LoginSession.account_id == account.id))
            db.delete(account)
            db.commit()

        if document_id:
            document = db.get(Document, document_id)
            assert document is not None and document.status == 'ENTREGADO'
            result = ProcessingResult.model_validate(document.processing_result)
            destination = db.get(Destination, result.routing.destination)
            assert destination and destination.slack_webhook_url
            payload = notification_payload(document, result, settings,
                event='DELIVERED', destination_name=destination.name)
            payload['blocks'][0]['text']['text'] = '🔗 MediFlow · Enlace actualizado'
            payload['blocks'][1]['text']['text'] = '<!channel> El enlace de este documento ya está disponible con HTTPS.'
            payload['text'] = payload['text'].replace('📥 MediFlow · Documento entregado', '🔗 MediFlow · Enlace actualizado')
            url = base + '/documents/' + str(document_id)
            assert payload['blocks'][-1]['elements'][0]['url'] == url
            assert 'localhost' not in json.dumps(payload)
            now = datetime.now(UTC)
            db.execute(insert(SlackNotification).values(document_id=document_id, level='LINK_FIX',
                destination_code=destination.code, status='PENDING', payload=payload,
                attempts=0, retryable=True, retry_at=now, created_at=now)
                .on_conflict_do_nothing(constraint='uq_slack_document_level'))
            db.commit()
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                db.expire_all()
                notice = db.scalar(select(SlackNotification).where(
                    SlackNotification.document_id == document_id, SlackNotification.level == 'LINK_FIX'))
                if notice.status == 'SENT':
                    break
                assert notice.status not in ('UNKNOWN', 'FAILED'), notice.error_code
                time.sleep(2)
            else:
                raise RuntimeError('Timed out waiting for the corrected Slack link')
            with httpx.Client(timeout=20) as client:
                assert client.get(url).status_code == 200
            report['slack'] = {'notification_id': notice.id, 'status': notice.status,
                'document_id': str(document_id), 'original_filename': document.original_filename,
                'destination_code': destination.code, 'url': url,
                'attempts': notice.attempts, 'sent_at': notice.sent_at.isoformat()}
    report['passed'] = True
    report['completed_at'] = datetime.now(UTC).isoformat()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--notify-document', type=UUID)
    args = parser.parse_args()
    run(args.report, args.notify_document)
