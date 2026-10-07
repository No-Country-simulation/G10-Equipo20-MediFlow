"""Shared documentary contracts. Required groups express sufficiency, not clinical correctness."""
from typing import Literal

DocumentType = Literal[
    "ECHOCARDIOGRAM_REPORT", "SPIROMETRY_REPORT", "CHEST_IMAGING_REPORT", "ECG_REPORT",
    "DISCHARGE_SUMMARY", "LABORATORY_RESULT", "LABORATORY_ORDER", "PRESCRIPTION",
    "PROCEDURE_ORDER", "MEDICAL_CERTIFICATE", "IMAGING_REPORT", "OTHER", "UNKNOWN",
]
Specialty = Literal["CARDIOLOGY", "PULMONOLOGY", "CARDIOPULMONARY", "LABORATORY",
                    "GENERAL_MEDICINE", "RADIOLOGY", "OTHER", "UNKNOWN"]

DISCHARGE_REQUIRED_FIELDS = (
    "patient_name", "patient_age", "professional_name", "document_date",
    "discharge_diagnosis", "discharge_treatment", "follow_up",
)

# Alternatives preserve established field names in cardiopulmonary extractions.
REQUIRED_GROUPS = {
    "ECHOCARDIOGRAM_REPORT": (("fraccion_eyeccion", "ejection_fraction", "findings", "conclusion"),),
    "SPIROMETRY_REPORT": (("fev1", "FEV1", "vef1", "findings", "conclusion"),),
    "CHEST_IMAGING_REPORT": (("findings", "conclusion", "hallazgos", "conclusion_estudio"),),
    "ECG_REPORT": (("findings", "conclusion", "rhythm", "ritmo", "frecuencia_cardiaca"),),
    "DISCHARGE_SUMMARY": tuple((name,) for name in DISCHARGE_REQUIRED_FIELDS),
    "LABORATORY_RESULT": (("patient_name",), ("test_name",), ("test_result",)),
    "LABORATORY_ORDER": (("patient_name",), ("ordered_test",)),
    "PRESCRIPTION": (("patient_name",), ("medication_name",), ("medication_dose",), ("medication_frequency",)),
    "PROCEDURE_ORDER": (("patient_name",), ("requested_procedure",)),
    "MEDICAL_CERTIFICATE": (("patient_name",), ("professional_name",), ("certificate_purpose",)),
    "IMAGING_REPORT": (("study_name",), ("findings", "conclusion")),
}

LABELS = {
    "ECHOCARDIOGRAM_REPORT": "Ecocardiograma", "SPIROMETRY_REPORT": "Espirometría",
    "CHEST_IMAGING_REPORT": "Informe de tórax", "ECG_REPORT": "Informe de ECG",
    "DISCHARGE_SUMMARY": "Epicrisis / informe de alta", "LABORATORY_RESULT": "Resultados de laboratorio",
    "LABORATORY_ORDER": "Orden de laboratorio", "PRESCRIPTION": "Receta médica",
    "PROCEDURE_ORDER": "Orden de procedimiento", "MEDICAL_CERTIFICATE": "Certificado médico",
    "IMAGING_REPORT": "Informe de imágenes", "OTHER": "Otro", "UNKNOWN": "Sin determinar",
}
SPECIALTY_LABELS = {
    "CARDIOLOGY": "Cardiología", "PULMONOLOGY": "Neumología", "CARDIOPULMONARY": "Cardiopulmonar",
    "LABORATORY": "Laboratorio", "GENERAL_MEDICINE": "Medicina general", "RADIOLOGY": "Radiología",
    "OTHER": "Otro", "UNKNOWN": "Sin determinar",
}
COMMON_FIELDS = ("patient_name", "patient_age", "patient_identity", "professional_name", "professional_license", "document_date",
                 "diagnosis", "diagnosis_code", "study_name", "findings", "conclusion", "priority_signal")
TYPE_FIELDS = {
    "DISCHARGE_SUMMARY": DISCHARGE_REQUIRED_FIELDS,
    "LABORATORY_RESULT": ("test_name", "test_result", "reference_range"),
    "LABORATORY_ORDER": ("ordered_test",),
    "PRESCRIPTION": ("medication_name", "medication_dose", "medication_frequency", "medication_route",
                     "medication_duration", "medication_concentration"),
    "PROCEDURE_ORDER": ("requested_procedure", "procedure_indication"),
    "MEDICAL_CERTIFICATE": ("certificate_purpose", "certificate_period"),
}


def document_catalog():
    return {"types": [{"code": code, "name": name,
                       "fields": list(dict.fromkeys((*COMMON_FIELDS, *TYPE_FIELDS.get(code, ())))),
                       "required_groups": [list(group) for group in REQUIRED_GROUPS.get(code, ())]}
                      for code, name in LABELS.items()],
            "specialties": [{"code": code, "name": name} for code, name in SPECIALTY_LABELS.items()],
            "rule_version": "documentary-v4"}


def completeness(kind: str | None, fields) -> float:
    groups = REQUIRED_GROUPS.get(kind, ())
    names = {field.name for field in fields if field.value.strip()}
    return sum(any(name in names for name in group) for group in groups) / len(groups) if groups else 0.0
