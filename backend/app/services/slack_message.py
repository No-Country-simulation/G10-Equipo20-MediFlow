"""Shared Slack Block Kit presentation for priority and inbox notifications."""
from datetime import UTC, datetime

from app.core.document_catalog import LABELS

PRIORITIES = {'ROUTINE': 'Rutina', 'URGENT': 'Urgente', 'CRITICAL': 'Crítica'}
FIELD_LABELS = {
    'patient_name': 'nombre del paciente', 'patient_identity': 'identificación del paciente',
    'medication_name': 'nombre del medicamento', 'medication_dose': 'dosis del medicamento',
    'medication_frequency': 'frecuencia de administración', 'ordered_test': 'prueba solicitada',
    'study_name': 'nombre del estudio', 'findings': 'hallazgos', 'conclusion': 'conclusión',
}


def escape_slack(value):
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def review_reasons(issues):
    reasons = []
    for issue in issues:
        if issue.startswith('MISSING_REQUIRED_FIELD:'):
            field = issue.split(':', 1)[1]
            reason = 'Falta ' + FIELD_LABELS.get(field, field.replace('_', ' ')) + '.'
        elif issue.startswith('INCOMPLETE_ENTITY:'):
            reason = 'Hay un tratamiento o resultado con datos incompletos.'
        elif issue == 'LOW_DOCUMENT_QUALITY':
            reason = 'La calidad documental está por debajo del umbral configurado.'
        elif issue == 'PRIORITY_AMBIGUOUS':
            reason = 'La prioridad necesita confirmación humana.'
        elif issue.startswith('FIELD_'):
            reason = 'Hay campos con evidencia no verificada o contradictoria.'
        else:
            reason = issue.replace('_', ' ').capitalize()
        if reason not in reasons:
            reasons.append(reason)
    return reasons


def notification_payload(document, result, settings, *, event, destination_name):
    priority = result.priority if result else None
    level = PRIORITIES.get(priority.level, 'Pendiente') if priority else 'Pendiente'
    classification = result.classification if result else None
    kind = LABELS.get(classification.document_type, classification.document_type) if classification else 'Pendiente de clasificación'
    if event == 'REVIEW':
        title, action, status = '🟠 MediFlow · Revisión humana', 'Hay un documento que requiere revisión.', 'Pendiente de revisión humana'
    elif event == 'DELIVERED':
        title, action, status = '📥 MediFlow · Documento entregado', 'Hay un nuevo documento disponible en la bandeja.', 'Entregado a bandeja local'
    else:
        title = '🚨 MediFlow · Prioridad ' + level.lower()
        action, status = 'El documento declara prioridad ' + level.lower() + '. Verifica el original.', 'Alerta de prioridad · procesamiento en curso'
    filename = document.original_filename
    summary = (f'<!channel> {title}\nArchivo: {escape_slack(filename)}\n'
               f'Bandeja: {escape_slack(destination_name)} · Prioridad: {level}\n'
               f'Estado: {status}\nDocumento: {document.document_id}')
    blocks = [
        {'type': 'header', 'text': {'type': 'plain_text', 'text': title, 'emoji': True}},
        {'type': 'section', 'text': {'type': 'mrkdwn', 'text': '<!channel> ' + action, 'verbatim': True}},
        {'type': 'section', 'text': {'type': 'plain_text', 'text': 'Archivo original\n' + filename}},
        {'type': 'section', 'fields': [
            {'type': 'plain_text', 'text': label + '\n' + value}
            for label, value in [('Bandeja', destination_name), ('Estado', status),
                                 ('Prioridad', level), ('País', document.country), ('Tipo documental', kind)]
        ]},
    ]
    if event == 'REVIEW' and result and result.validation:
        reasons = review_reasons(result.validation.issues)
        if reasons:
            detail = 'Motivos de revisión\n' + '\n'.join('• ' + reason for reason in reasons[:10])
            if len(reasons) > 10:
                detail += f'\n• Y {len(reasons) - 10} motivos adicionales; consulta MediFlow.'
            blocks.append({'type': 'section', 'text': {'type': 'plain_text', 'text': detail[:2900]}})
            summary += '\n' + escape_slack(detail[:2900])
    blocks.append({'type': 'context', 'elements': [{'type': 'plain_text',
        'text': f'ID: {document.document_id} · {datetime.now(UTC):%d/%m/%Y %H:%M UTC}'}]})
    base = settings.public_frontend_url.rstrip('/')
    if base:
        url = f'{base}/documents/{document.document_id}'
        blocks.append({'type': 'actions', 'elements': [{'type': 'button',
            'text': {'type': 'plain_text', 'text': 'Abrir documento en MediFlow'},
            'url': url, 'action_id': 'open_document', 'style': 'primary'}]})
        summary += '\n' + url
    return {'text': summary, 'blocks': blocks, 'unfurl_links': False, 'unfurl_media': False}
