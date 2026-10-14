"""Upload and verify three Colombian documents with real OCR, R2 and Slack.

Run explicitly against the API environment. Sends real Slack notifications.
Existing IDs in the report are reused so rerunning does not duplicate uploads.
"""
import argparse
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import secrets
import time
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.auth import token_hash
from app.core.config import get_settings
from app.core.database import get_engine
from app.models.account import Account, LoginSession
from app.models.destination import Destination
from app.models.execution import ResultBackup
from app.models.document import Document
from app.models.notification import SlackNotification
from app.services.storage import get_storage
from app.services.notifications import valid_slack_webhook

CASES = [
    ('01_imagenes_escaneado.pdf', 'DIAGNOSTICO_IMAGENES', 'ENTREGADO', 'IMAGING_REPORT', '1099900101', True),
    ('02_urgencias_ocr.png', 'COLA_URGENCIAS_MEDICAS', 'ENTREGADO', 'LABORATORY_ORDER', '1099900102', True),
    ('03_revision_humana.pdf', 'REVISION_HUMANA', 'EN_REVISION_HUMANA', 'PRESCRIPTION', '1099900103', False),
]


def run(directory, report_path):
    report = json.loads(report_path.read_text()) if report_path.exists() else {'country': 'CO', 'cases': {}}
    def save():
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    token = secrets.token_urlsafe(32)
    settings = get_settings()
    with Session(get_engine()) as db:
        admin = db.scalar(select(Account).where(Account.role == 'SUPERADMIN', Account.active.is_(True)))
        if admin is None:
            raise RuntimeError('Active administrator not found')
        login = LoginSession(token_hash=token_hash(token), account_id=admin.id,
                             expires_at=datetime.now(UTC) + timedelta(minutes=30))
        db.add(login); db.commit()
        try:
            general = settings.slack_webhook_url.get_secret_value().strip()
            urgent = settings.slack_webhook_url_urgente.get_secret_value().strip()
            configured = db.scalars(select(Destination).where(Destination.active.is_(True))).all()
            assert all(valid_slack_webhook(d.slack_webhook_url) for d in configured), 'Inbox webhook is missing or invalid'
            assert next(d for d in configured if d.code == 'COLA_URGENCIAS_MEDICAS').slack_webhook_url == urgent
            report['inboxes'] = [{'code': d.code, 'configured': bool(d.slack_webhook_url),
                'source': 'SLACK_WEBHOOK_URL_URGENTE' if d.code == 'COLA_URGENCIAS_MEDICAS'
                    else 'SLACK_WEBHOOK_URL' if d.slack_webhook_url == general else 'DESTINATION_WEBHOOK'} for d in configured]
            with httpx.Client(base_url='http://frontend', cookies={'mediflow_session': token}, timeout=30) as client:
                def request(method, path, **kwargs):
                    response = client.request(method, '/api' + path, **kwargs)
                    if response.status_code >= 400:
                        # API errors are documentary codes, never Slack URLs.
                        raise RuntimeError(f'{method} {path}: HTTP {response.status_code} {response.text[:1000]}')
                    return response
                assert request('GET', '/config').json()['default_country'] == 'CO'
                for filename, destination, status, kind, identity, ocr in CASES:
                    path = directory / filename
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    item = report['cases'].get(filename)
                    if item:
                        assert item['sha256'] == digest, 'Fixture changed; use a new report to create another run'
                    else:
                        with path.open('rb') as file:
                            uploaded = request('POST', '/documents', data={'country': 'CO'}, files={'file':
                                (filename, file, 'image/png' if filename.endswith('.png') else 'application/pdf')}).json()
                        item = {'document_id': uploaded['document_id'], 'sha256': digest, 'expected_destination': destination}
                        report['cases'][filename] = item
                        save()
                        request('POST', f"/documents/{item['document_id']}/processing-jobs")
                        print(f"UPLOADED {filename}: {item['document_id']}", flush=True)
                deadline = time.monotonic() + 600
                last = {}
                while time.monotonic() < deadline:
                    all_done = True
                    for filename, destination, status, kind, identity, ocr in CASES:
                        item = report['cases'][filename]
                        document_id = item['document_id']
                        document = request('GET', f'/documents/{document_id}').json()
                        current = document['status']
                        if current != last.get(filename):
                            print(f'{filename}: {current}', flush=True); last[filename] = current
                        if current not in ('ENTREGADO', 'EN_REVISION_HUMANA', 'FALLO_TECNICO', 'RECHAZADO'):
                            all_done = False
                            continue
                        result = request('GET', f'/documents/{document_id}/result').json()
                        notifications = request('GET', f'/documents/{document_id}/notifications').json()
                        stored_notices = db.scalars(select(SlackNotification).where(
                            SlackNotification.document_id == UUID(document_id))).all()
                        for notice in stored_notices:
                            assert notice.payload['text'].startswith('<!channel>'), 'Missing Slack broadcast'
                            assert filename in notice.payload['text'], 'Missing original filename in Slack fallback'
                            blocks = notice.payload.get('blocks', [])
                            assert any(b.get('type') == 'header' for b in blocks), 'Missing Slack design header'
                            assert any(filename in b.get('text', {}).get('text', '') for b in blocks), 'Missing filename in Slack blocks'
                            assert any('<!channel>' in b.get('text', {}).get('text', '') for b in blocks), 'Missing Slack broadcast block'
                        item['slack_design_verified'] = bool(stored_notices)
                        job = request('GET', f'/documents/{document_id}/processing-jobs/latest').json()
                        item.update({'status': current, 'country': document['country'], 'classification': result['classification'],
                            'priority': result['priority'], 'quality': result['quality'], 'patient': result['patient'],
                            'issues': result['validation']['issues'] if result['validation'] else [],
                            'methods': [p['method'] for p in result['content']['pages']] if result['content'] else [],
                            'field_checks': result['validation']['field_checks'] if result['validation'] else [],
                            'provider_calls': job['provider_calls'], 'notifications': notifications,
                            'error_code': result['error_code']})
                        save()
                        assert current == status, (filename, 'Unexpected status', current, item['issues'], result['error_code'])
                        assert document['country'] == 'CO'
                        assert result['classification']['document_type'] == kind, (filename, result['classification'])
                        assert result['patient']['identity_number'] == identity, (filename, result['patient'])
                        assert result['patient']['status'] in ('CREATED', 'LINKED')
                        if ocr:
                            assert item['methods'] and all(m in ('openai_ocr', 'gemini_ocr') for m in item['methods'])
                            assert job['provider_calls'].get('ocr') == 1, (filename, job['provider_calls'])
                        else:
                            assert item['methods'] == ['embedded_text']
                        if status == 'ENTREGADO':
                            assert result['routing']['destination'] == destination
                            assert result['routing']['delivery_status'] == 'DELIVERED_LOCAL'
                            assert result['validation']['valid'] and not item['issues']
                        else:
                            assert result['routing'] is None
                            assert 'MISSING_REQUIRED_FIELD:medication_frequency' in item['issues']
                        expected_priority = 'URGENT' if destination == 'COLA_URGENCIAS_MEDICAS' else 'ROUTINE'
                        assert result['priority']['level'] == expected_priority
                        assert not result['priority']['ambiguous']
                        inbox = request('GET', '/documents', params={'country': 'CO', 'destination': destination,
                            'q': document_id}).json()
                        assert document_id in {d['document_id'] for d in inbox['items']}, (filename, 'Absent from inbox')
                        own = [n for n in notifications if n['destination_code'] == destination]
                        assert len(own) <= 1, 'Duplicate destination outbox records'
                        if not own or any(n['status'] == 'PENDING' or n['will_retry'] for n in notifications):
                            all_done = False
                        else:
                            assert all(n['status'] == 'SENT' for n in notifications), (filename, notifications)
                            assert own[0]['status'] == 'SENT'
                        db.expire_all()
                        backup = db.scalar(select(ResultBackup).where(ResultBackup.document_id == UUID(document_id))
                            .order_by(ResultBackup.id.desc()).limit(1))
                        item['backup_status'] = backup.status if backup else None
                        if not backup or backup.status != 'SYNCED':
                            all_done = False
                    save()
                    if all_done:
                        break
                    time.sleep(3)
                else:
                    raise RuntimeError('Timed out waiting for processing, Slack or R2 backups; inspect report')
                for filename, *_ in CASES:
                    item = report['cases'][filename]
                    original = request('GET', f"/documents/{item['document_id']}/file").content
                    assert hashlib.sha256(original).hexdigest() == item['sha256'], 'R2 original changed'
                    item['r2_original_verified'] = True
                    stored_document = db.get(Document, UUID(item['document_id']))
                    assert stored_document.storage_backend == 'r2'
                    backup = db.scalar(select(ResultBackup).where(ResultBackup.document_id == stored_document.document_id)
                        .order_by(ResultBackup.id.desc()).limit(1))
                    storage = get_storage(settings, stored_document.storage_backend, stored_document.storage_bucket)
                    with storage.materialize(backup.storage_key, settings.max_upload_bytes) as snapshot:
                        snapshot_data = json.loads(snapshot.read_text())
                        assert snapshot_data == backup.payload, 'R2 backup content differs from recorded snapshot'
                        assert snapshot_data['document_id'] == item['document_id']
                        assert snapshot_data['metadata']['original_filename'] == filename
                        assert snapshot_data['result']['status'] == item['status']
                    item['r2_backup_verified'] = True
                    item['original_storage_key'] = stored_document.storage_key
                    item['backup_storage_key'] = backup.storage_key
                    item['slack_payloads'] = [{'level': notice.level, 'destination_code': notice.destination_code,
                        'payload': notice.payload, 'status': notice.status} for notice in db.scalars(
                            select(SlackNotification).where(SlackNotification.document_id == stored_document.document_id))]
                    item['passed'] = True
                report['completed_at'] = datetime.now(UTC).isoformat()
                report['passed'] = True
                report.pop('failure', None)
                save()
                print('PASS: three Colombian cases, OCR, fields, inboxes, real Slack and R2 verified.', flush=True)
        except Exception as exc:
            report['passed'] = False
            report['failure'] = str(exc)
            save()
            raise
        finally:
            db.delete(login); db.commit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixtures', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    run(args.fixtures, args.report)
