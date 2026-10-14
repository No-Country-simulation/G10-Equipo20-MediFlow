from pathlib import Path

import pytest
from app.schemas.processing import ContentPage, ContentResult, Evidence, ExtractionResult, ExtractedField, ClassificationResult
from app.services.identity_detection import detect_labeled_identity, complete_identity
from app.services.patients import validate_identity
from app.services.triage import detect_priority, precautionary_signal
from app.graph.processing import build_processing_graph
from app.core.config import Settings


def content(text):
    return ContentResult(pages=[ContentPage(page=1, text=text, method='embedded_text')])


@pytest.mark.parametrize('country,text,number', [
    ('CO', 'DOCUMENTO\nC.C. 70.093.851\nPACIENTE\nPersona de Prueba\nFirma y Sello del Médico\nDr. Otro Profesional\nRegistro Médico (ReTHUS) N° 79.654.210 · C.C.\n79.654.210', '70093851'),
    ('CO', 'Paciente: Persona de Prueba\nDocumento\n\nC.C.\n\n70.093.851', '70093851'),
    ('PE', 'Paciente: Persona de Prueba\nDNI: 12345678\nFirma del médico\nDNI: 87654321', '12345678'),
    ('EC', 'Paciente: Persona de Prueba\nC.I. 1710034065\nAcudiente: Otra Persona\nC.I. 1700000001', '1710034065'),
    ('AR', 'Patient: Test Person\nDNI 12.345.678', '12345678'),
    ('BR', 'Paciente: Teste Pessoa\nCPF 123.456.789-01', '12345678901'),
    ('CL', 'Paciente: Persona de Prueba\nRUN 12.345.678-K', '12345678K'),
    ('CO', 'INFORME MÉDICO\nDOCUMENTO: 12.345.678\nPACIENTE: Persona de Prueba', '12345678'),
])
def test_patient_id_role_and_multiline(country, text, number):
    detected = detect_labeled_identity(content(text), country)
    assert detected is not None
    assert validate_identity(country, detected.value)[1] == number
    assert detected.evidence.quote in text


@pytest.mark.parametrize('text,country', [
    ('Firma y Sello del Médico\nDr. Otra Persona\nC.C. 79.654.210', 'CO'),
    ('Paciente: Persona de Prueba\nC.C. 12.345.678\nC.C. 87.654.321', 'CO'),
    ('Documento: FM-2024-0058\nPaciente: Persona de Prueba', 'CO'),
    ('Paciente: Persona de Prueba\nDNI: 12345678', 'CO'),
    ('NIT 901.458.723-1\nTeléfono 7456820\nPaciente: Persona de Prueba', 'CO'),
    ('Acudiente: Otra Persona\nC.C. 12.345.678', 'CO'),
    ('Dr. Otra Persona\nC.C. 12.345.678', 'CO'),
])
def test_do_not_guess_identity(text, country):
    assert detect_labeled_identity(content(text), country) is None


@pytest.mark.parametrize('text', [
    '• Consultar de inmediato ante sangrado, heces negras u orina oscura.',
    'Acudir a evaluación urgente si presenta dolor.',
    'Buscar atención inmediata en caso de fiebre.',
    'Seek immediate attention if symptoms worsen.',
    'Procurar atenção imediata caso apresente febre.',
])
def test_conditional_advice_is_not_current_urgency(text):
    source = content(text)
    assert precautionary_signal(source, Evidence(page=1, quote=text))
    priority = detect_priority(source)
    assert priority.level == 'ROUTINE'
    assert not priority.ambiguous


@pytest.mark.parametrize('text,level', [
    ('Prioridad: urgente', 'URGENT'),
    ('Se requiere evaluación urgente ahora.', 'URGENT'),
    ('Resultado crítico confirmado.', 'CRITICAL'),
])
def test_active_urgency_retained(text, level):
    priority = detect_priority(content(text))
    assert priority.level == level
    assert not priority.ambiguous


def test_graph_with_patient_and_signer_and_preventive_advice(tmp_path):
    text = ('FÓRMULA MÉDICA\nDOCUMENTO\nC.C. 70.093.851\nPACIENTE\nPersona de Prueba\n'
            'Medicamento 5 mg cada 24 horas\n'
            '• Consultar de inmediato ante sangrado, heces negras u orina oscura.\n'
            'Firma y Sello del Médico\nDr. Otro Profesional\nC.C. 79.654.210')
    source = content(text)
    def field(name, value, quote):
        return ExtractedField(name=name, value=value, unit=None, evidence=Evidence(page=1, quote=quote))
    extraction = ExtractionResult(fields=[
        field('patient_name', 'Persona de Prueba', 'PACIENTE\nPersona de Prueba'),
        field('medication_name', 'Medicamento', 'Medicamento 5 mg cada 24 horas'),
        field('medication_dose', '5 mg', 'Medicamento 5 mg cada 24 horas'),
        field('medication_frequency', 'cada 24 horas', 'Medicamento 5 mg cada 24 horas'),
        field('priority_signal', 'Consultar de inmediato ante sangrado, heces negras u orina oscura.',
              '• Consultar de inmediato ante sangrado, heces negras u orina oscura.'),
    ])
    class Provider:
        def classify(self, *args):
            raise AssertionError('Cached classification must be reused')
        def extract(self, *args):
            raise AssertionError('Cached extraction must be reused')
    path = tmp_path / 'source.txt'
    path.write_text(text)
    result = build_processing_graph(Provider(), Settings(postgres_password='test')).invoke({
        'document_id': 'test', 'path': path, 'format': 'pdf', 'country': 'CO', 'content': source,
        'classification': ClassificationResult(document_type='PRESCRIPTION', specialty='CARDIOLOGY',
            evidence=Evidence(page=1, quote='FÓRMULA MÉDICA'), reason='literal'), 'extraction': extraction})
    assert result['validation'].valid, result['validation'].issues
    assert result['quality'].score == 1
    assert result['patient'].identity_number == '70093851'
    assert result['routing'].destination == 'FARMACIA_HOSPITALARIA'
    assert len([f for f in result['extraction'].fields if f.name == 'patient_identity']) == 1
    assert complete_identity(source, result['extraction'], 'CO') == result['extraction']


def test_multiple_patient_ids_are_conflicts_not_missing():
    from app.services.processing_validation import validate_processing
    source = content('Paciente: Persona de Prueba\nC.C. 12.345.678\nC.C. 87.654.321')
    extraction = complete_identity(source, ExtractionResult(fields=[]), 'CO')
    assert len(extraction.fields) == 2
    validation = validate_processing(source, None, extraction, country='CO')
    assert 'FIELD_CONFLICT:patient_identity' in validation.issues


def test_disagreeing_model_identity_is_preserved_for_review():
    source = content('Paciente: Persona de Prueba\nC.C. 12.345.678\nFirma del médico\nC.C. 87.654.321')
    model = ExtractionResult(fields=[ExtractedField(name='patient_identity', value='87.654.321', unit=None,
        evidence=Evidence(page=1, quote='Firma del médico\nC.C. 87.654.321'))])
    completed = complete_identity(source, model, 'CO')
    assert {field.value for field in completed.fields} == {'12.345.678', '87.654.321'}
