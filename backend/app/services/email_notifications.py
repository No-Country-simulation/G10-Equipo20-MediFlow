"""Optional SMTP notifications. Disabled until explicitly configured and enabled."""
import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.administration import ConfigurationVariable
from app.models.destination import Destination
from app.models.notification import EmailNotification


class SMTPInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = False
    host: str = Field(default='', max_length=255, pattern=r'^[a-zA-Z0-9.\-]*$')
    port: int = Field(default=587, ge=1, le=65535)
    security: Literal['STARTTLS', 'SSL_TLS'] = 'STARTTLS'
    username: str = Field(default='', max_length=255)
    password: SecretStr | None = None
    sender: EmailStr | Literal[''] = ''
    # Preserve passwords exactly; whitespace can be a valid credential.
    clear_password: bool = False

    @field_validator('host', 'username', 'sender', 'security', mode='before')
    @classmethod
    def trim_configuration_fields(cls, value):
        return value.strip() if isinstance(value, str) else value


SMTP_DEFAULTS = {'enabled': 'false', 'host': '', 'port': '587', 'security': 'STARTTLS',
                 'username': '', 'password': '', 'sender': ''}
SMTP_KEYS = {'SMTP_' + name.upper() for name in SMTP_DEFAULTS}


def smtp_configuration(session):
    values = dict(session.execute(select(ConfigurationVariable.name, ConfigurationVariable.value)
                                 .where(ConfigurationVariable.name.in_(SMTP_KEYS))).all())
    return {name: values.get('SMTP_' + name.upper(), default) for name, default in SMTP_DEFAULTS.items()}


def public_smtp(configuration):
    return {name: value for name, value in configuration.items() if name != 'password'} | {
        'enabled': configuration['enabled'] == 'true', 'port': int(configuration['port']),
        'password_configured': bool(configuration['password'])}


def save_smtp(session, request: SMTPInput):
    configuration = smtp_configuration(session)
    configuration.update({name: str(value) for name, value in request.model_dump(
        exclude={'password', 'clear_password', 'enabled'}).items()})
    configuration['enabled'] = 'true' if request.enabled else 'false'
    if request.clear_password:
        configuration['password'] = ''
    elif request.password is not None:
        configuration['password'] = request.password.get_secret_value()
    if request.enabled and not all(configuration[key] for key in ('host', 'sender', 'username', 'password')):
        raise ValueError('SMTP_CONFIGURATION_INCOMPLETE')
    for name, value in configuration.items():
        session.execute(insert(ConfigurationVariable).values(name='SMTP_' + name.upper(), value=value)
                        .on_conflict_do_update(index_elements=['name'], set_={'value': value}))
    return public_smtp(configuration)


def schedule_email_notification(session, document, destination, event, settings):
    if not destination.active or not destination.emails or smtp_configuration(session)['enabled'] != 'true':
        return
    now = datetime.now(UTC)
    # Keep clinical fields and attachments out of email; access remains authenticated.
    payload = {'subject': 'MediFlow · ' + ('Documento por revisar' if event == 'REVIEW' else 'Documento disponible'),
               'body': f'Hay un documento en la bandeja {destination.name}.\n'
                       f'Abre MediFlow para consultarlo: {settings.public_frontend_url.rstrip("/")}/documents/{document.document_id}'}
    session.execute(insert(EmailNotification).values(document_id=document.document_id,
        destination_code=destination.code, event=event, status='PENDING', payload=payload,
        attempts=0, created_at=now, retry_at=now)
        .on_conflict_do_nothing(constraint='uq_email_document_event'))


class SMTPNotifier:
    def send(self, configuration, recipients, payload):
        message = EmailMessage()
        message['Subject'], message['From'] = payload['subject'], configuration['sender']
        message['To'] = configuration['sender']
        message.set_content(payload['body'])
        context = ssl.create_default_context()
        connection = smtplib.SMTP_SSL if configuration['security'] == 'SSL_TLS' else smtplib.SMTP
        options = {'timeout': 10}
        if configuration['security'] == 'SSL_TLS':
            options['context'] = context
        with connection(configuration['host'], int(configuration['port']), **options) as smtp:
            if configuration['security'] == 'STARTTLS':
                smtp.starttls(context=context)
            smtp.login(configuration['username'], configuration['password'])
            refused = smtp.send_message(message, to_addrs=recipients)
            if refused:
                # Some recipients may already have received it; do not duplicate.
                raise smtplib.SMTPRecipientsRefused(refused)


def process_email_notification(session, settings, transport=None):
    configuration = smtp_configuration(session)
    if configuration['enabled'] != 'true':
        session.commit()
        return False
    row = session.scalar(select(EmailNotification).where(EmailNotification.status.in_(('PENDING', 'FAILED')),
        EmailNotification.attempts < 3, EmailNotification.retry_at <= datetime.now(UTC))
        .order_by(EmailNotification.id).with_for_update(skip_locked=True).limit(1))
    if row is None:
        session.commit()
        return False
    destination = session.get(Destination, row.destination_code)
    row.attempts += 1
    if destination is None or not destination.active or not destination.emails:
        row.status, row.error_code = 'CANCELLED', 'EMAIL_DESTINATION_UNAVAILABLE'
    else:
        try:
            (transport or SMTPNotifier()).send(configuration, destination.emails, row.payload)
            row.status, row.sent_at, row.error_code = 'SENT', datetime.now(UTC), None
        except (smtplib.SMTPServerDisconnected, TimeoutError, smtplib.SMTPRecipientsRefused):
            row.status, row.error_code = 'UNKNOWN', 'SMTP_DELIVERY_UNCERTAIN'
        except (smtplib.SMTPException, OSError):
            row.status, row.error_code = 'FAILED', 'SMTP_UNAVAILABLE'
            row.retry_at = datetime.now(UTC) + timedelta(seconds=30 * 2 ** row.attempts)
    session.commit()
    return True
