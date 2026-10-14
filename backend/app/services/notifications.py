"""Adapted from Cesar-Barrera's webhook transport, with a PostgreSQL outbox.

Priority alerts use the urgent webhook; general inboxes use their configured webhook.
No SMTP. Webhooks cannot guarantee exactly-once delivery after a lost response.
"""
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
import re
import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.models.notification import SlackNotification
from app.services.slack_message import notification_payload


class SlackError(Exception):
    def __init__(self, code, *, retryable=False, uncertain=False, retry_after=30):
        self.code, self.retryable, self.uncertain, self.retry_after = code, retryable, uncertain, retry_after


def valid_slack_webhook(webhook: str) -> bool:
    try:
        parsed = urlsplit(webhook)
    except ValueError:
        return False
    return (parsed.scheme == 'https' and parsed.netloc in ('hooks.slack.com', 'hooks.slack.com:443')
            and not parsed.query and not parsed.fragment and not parsed.username
            and bool(re.fullmatch(r'/services/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+', parsed.path)))


class SlackNotifier:
    def __init__(self, settings):
        self.settings = settings

    def send(self, level, payload, *, webhook=None):
        primary = self.settings.slack_webhook_url.get_secret_value().strip()
        urgent = self.settings.slack_webhook_url_urgente.get_secret_value().strip()
        if webhook is None:
            webhook = (urgent or primary) if level in ('URGENT', 'CRITICAL') else primary
        if not webhook:
            raise SlackError('SLACK_NOT_CONFIGURED')
        if not valid_slack_webhook(webhook):
            raise SlackError('SLACK_INVALID_WEBHOOK')
        try:
            # No implicit retries and no URL/response body in errors or logs.
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                response = client.post(webhook, json=payload)
        except httpx.ConnectError:
            raise SlackError('SLACK_CONNECTION_FAILED', retryable=True) from None
        except httpx.ConnectTimeout:
            raise SlackError('SLACK_CONNECTION_FAILED', retryable=True) from None
        except httpx.HTTPError:
            raise SlackError('SLACK_DELIVERY_UNCERTAIN', uncertain=True) from None
        if response.status_code == 200 and response.text.strip() == 'ok':
            return
        if response.status_code == 429:
            raw = response.headers.get('Retry-After', '30')
            wait = min(3600, max(1, int(raw))) if raw.isdigit() else 30
            raise SlackError('SLACK_RATE_LIMITED', retryable=True, retry_after=wait)
        if response.status_code >= 500:
            raise SlackError('SLACK_UNAVAILABLE', retryable=True)
        raise SlackError('SLACK_REQUEST_REJECTED')


def notification_eligibility(result):
    """Explain the same criteria used by the outbox; never infer clinical urgency."""
    if result is None or result.priority is None:
        return False, 'SLACK_PRIORITY_NOT_ASSESSED'
    priority = result.priority
    if priority.level == 'ROUTINE':
        return False, 'SLACK_ROUTINE_NOT_NOTIFIED'
    if priority.source != 'EXPLICIT' or priority.evidence is None:
        return False, 'SLACK_PRIORITY_NOT_CONFIRMED'
    from app.services.processing_validation import evidence_supported
    if not result.content or not evidence_supported(result.content, priority.evidence):
        return False, 'SLACK_PRIORITY_NOT_CONFIRMED'
    return True, 'SLACK_PRIORITY_CONFIRMED'


def notification_configuration(settings):
    primary = bool(settings.slack_webhook_url.get_secret_value().strip())
    urgent = bool(settings.slack_webhook_url_urgente.get_secret_value().strip())
    return {'critical_configured': urgent or primary, 'urgent_configured': urgent or primary,
            'urgent_uses_main_webhook': not urgent and primary}


def schedule_destination_notification(session, document, result, settings):
    # Human review is an operational inbox, not a clinical routing decision.
    # Queue its notice only once the final review state has been persisted.
    review = document.status == 'EN_REVISION_HUMANA'
    if review:
        destination_code, event = 'REVISION_HUMANA', 'REVIEW'
    elif (document.status == 'ENTREGADO' and result is not None and result.routing is not None
            and result.routing.delivery_status == 'DELIVERED_LOCAL'):
        destination_code, event = result.routing.destination, 'DELIVERED'
    else:
        return
    from app.models.destination import Destination
    destination = session.get(Destination, destination_code)
    if destination is None or not destination.slack_webhook_url:
        return
    payload = notification_payload(document, result, settings, event=event, destination_name=destination.name)
    now = datetime.now(UTC)
    session.execute(insert(SlackNotification).values(document_id=document.document_id,
        level=event, destination_code=destination.code, status='PENDING',
        payload=payload,
        attempts=0, retryable=True, created_at=now, retry_at=now)
        .on_conflict_do_nothing(constraint='uq_slack_document_level'))


def schedule_notification(session, document, result, settings):
    schedule_destination_notification(session, document, result, settings)
    if not notification_eligibility(result)[0]:
        return
    priority = result.priority
    payload = notification_payload(document, result, settings, event=priority.level,
                                   destination_name='Urgencias Médicas')
    now = datetime.now(UTC)
    session.execute(insert(SlackNotification).values(document_id=document.document_id, level=priority.level,
        status='PENDING', payload=payload,
        attempts=0, retryable=True, created_at=now, retry_at=now)
        .on_conflict_do_nothing(constraint='uq_slack_document_level'))


def process_notification(session, settings, notifier=None):
    row = session.scalar(select(SlackNotification).where(
        SlackNotification.status.in_(('PENDING', 'FAILED')), SlackNotification.retryable.is_(True),
        SlackNotification.attempts < settings.slack_max_attempts, SlackNotification.retry_at <= datetime.now(UTC))
        .order_by(SlackNotification.id).with_for_update(skip_locked=True).limit(1))
    if row is None:
        session.commit()
        return False
    row.attempts += 1
    try:
        transport = notifier or SlackNotifier(settings)
        if row.destination_code:
            from app.models.destination import Destination
            destination = session.get(Destination, row.destination_code)
            transport.send(row.level, row.payload, webhook=destination.slack_webhook_url if destination else '')
        else:
            transport.send(row.level, row.payload)
        row.status, row.error_code, row.sent_at, row.retryable = 'SENT', None, datetime.now(UTC), False
    except SlackError as exc:
        row.status = 'UNKNOWN' if exc.uncertain else 'FAILED'
        row.error_code = exc.code
        row.retryable = exc.retryable
        row.retry_at = datetime.now(UTC) + timedelta(seconds=max(exc.retry_after, min(3600, 30 * 2 ** row.attempts)))
    session.commit()
    return True
