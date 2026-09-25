import re

from app.schemas.processing import ClassificationResult, ContentResult, ExtractionResult, ValidationResult


DISCHARGE_REQUIRED_FIELDS = (
    "patient_name", "patient_age", "professional_name", "document_date",
    "discharge_diagnosis", "discharge_treatment", "follow_up",
)


def normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def literal_present(value: str, source: str) -> bool:
    # Limites de palabra evitan validar 5 contra 55 o un fragmento de otra palabra.
    value = normalized(value)
    if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)*", value):
        pattern = r"(?<![\w.,])" + re.escape(value) + r"(?!\w|[.,]\d)"
    else:
        pattern = r"(?<!\w)" + re.escape(value) + r"(?!\w)"
    return bool(value and re.search(pattern, normalized(source)))


def validate_processing(content: ContentResult, classification: ClassificationResult | None,
                        extraction: ExtractionResult | None) -> ValidationResult:
    pages = {page.page: page.text for page in content.pages}
    issues = []
    if not pages or any(not text.strip() for text in pages.values()):
        issues.append("EMPTY_OR_UNREADABLE_PAGE")
    if any(page.uncertain for page in content.pages):
        issues.append("OCR_UNCERTAIN")
    if classification is None or classification.document_type == "UNKNOWN":
        issues.append("CLASSIFICATION_UNCERTAIN")
    elif classification.document_type == "OTHER" or classification.specialty in ("OTHER", "UNKNOWN"):
        issues.append("OUTSIDE_INITIAL_SCOPE")
    if classification is not None:
        expected_specialty = {
            "ECHOCARDIOGRAM_REPORT": "CARDIOLOGY", "ECG_REPORT": "CARDIOLOGY",
            "SPIROMETRY_REPORT": "PULMONOLOGY", "CHEST_IMAGING_REPORT": "PULMONOLOGY",
        }.get(classification.document_type)
        if expected_specialty and classification.specialty not in (expected_specialty, "CARDIOPULMONARY"):
            issues.append("CLASSIFICATION_SPECIALTY_CONFLICT")
        evidence = classification.evidence
        if evidence is None or not literal_present(evidence.quote, pages.get(evidence.page, "")):
            issues.append("CLASSIFICATION_EVIDENCE_NOT_FOUND")
    if extraction is None or not extraction.fields:
        issues.append("NO_EXTRACTED_FIELDS")
    else:
        for index, field in enumerate(extraction.fields):
            source = pages.get(field.evidence.page, "")
            if not literal_present(field.evidence.quote, source):
                issues.append(f"FIELD_{index}_EVIDENCE_NOT_FOUND")
            elif not literal_present(field.value, field.evidence.quote):
                issues.append(f"FIELD_{index}_VALUE_NOT_SUPPORTED")
            if field.unit and not literal_present(field.unit, field.evidence.quote):
                issues.append(f"FIELD_{index}_UNIT_NOT_SUPPORTED")
    if classification and classification.document_type == "DISCHARGE_SUMMARY":
        present = {field.name for field in extraction.fields} if extraction else set()
        for name in DISCHARGE_REQUIRED_FIELDS:
            if name not in present:
                issues.append("MISSING_REQUIRED_FIELD:" + name)
    return ValidationResult(valid=not issues, requires_human_review=bool(issues), issues=issues, rule_version="documentary-v2")
