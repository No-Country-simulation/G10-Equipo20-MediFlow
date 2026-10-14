"""Associate environment webhooks to operational inboxes without exposing secrets.

Explicit administrative command, not a startup hook: later UI edits persist.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import get_engine
from app.models.destination import Destination, RoutingRule
from app.services.notifications import valid_slack_webhook


def configure():
    settings = get_settings()
    general = settings.slack_webhook_url.get_secret_value().strip()
    urgent = settings.slack_webhook_url_urgente.get_secret_value().strip()
    if not all(valid_slack_webhook(value) for value in (general, urgent)):
        raise RuntimeError('Both environment Slack webhooks must be valid')
    with Session(get_engine()) as session:
        destinations = session.scalars(select(Destination).with_for_update()).all()
        codes = {d.code for d in destinations}
        if not {'DIAGNOSTICO_IMAGENES', 'COLA_URGENCIAS_MEDICAS', 'REVISION_HUMANA'} <= codes:
            raise RuntimeError('Required operational inboxes are missing')
        for destination in destinations:
            # Explicit destination settings take precedence over the fallback.
            # Re-running setup must preserve channels edited by administrators.
            if destination.code == 'COLA_URGENCIAS_MEDICAS':
                destination.slack_webhook_url = urgent
            elif not destination.slack_webhook_url:
                destination.slack_webhook_url = general
        rule = session.scalar(select(RoutingRule).where(RoutingRule.document_type == 'IMAGING_REPORT',
                              RoutingRule.specialty == 'ANY').with_for_update())
        if rule:
            rule.destination_code, rule.active = 'DIAGNOSTICO_IMAGENES', True
        else:
            session.add(RoutingRule(document_type='IMAGING_REPORT', specialty='ANY',
                                   destination_code='DIAGNOSTICO_IMAGENES', active=True))
        session.commit()
        for destination in sorted(destinations, key=lambda d: d.code):
            source = ('SLACK_WEBHOOK_URL_URGENTE' if destination.code == 'COLA_URGENCIAS_MEDICAS'
                      else 'SLACK_WEBHOOK_URL' if destination.slack_webhook_url == general else 'DESTINATION_WEBHOOK')
            print(destination.code, source, 'OK')
        print('IMAGING_REPORT / ANY -> DIAGNOSTICO_IMAGENES: OK')


if __name__ == '__main__':
    configure()
