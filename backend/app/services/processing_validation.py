import re

from app.schemas.processing import ClassificationResult, ContentResult, ExtractionResult, ValidationResult
from app.core.document_catalog import DISCHARGE_REQUIRED_FIELDS, REQUIRED_GROUPS


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


def evidence_supported(content, evidence):
    if evidence is None:
        return False
    if content.pages and content.pages[0].page is None:
        text = content.pages[0].text
        return (evidence.page is None and evidence.start is not None and evidence.end is not None
                and evidence.start < evidence.end <= len(text)
                and text[evidence.start:evidence.end] == evidence.quote)
    return literal_present(evidence.quote, next((p.text for p in content.pages if p.page == evidence.page), ""))


def describe_validation(validation, extraction):
    from app.schemas.processing import ValidationIssue, FieldCheck
    fields = extraction.fields if extraction else []
    validation.details = []
    validation.field_checks = []
    for index, field in enumerate(fields):
        problems = [code for code in validation.issues if code.startswith(f"FIELD_{index}_")]
        if f"FIELD_CONFLICT:{field.name}" in validation.issues:
            problems.append(f"FIELD_CONFLICT:{field.name}")
        validation.field_checks.append(FieldCheck(index=index, name=field.name,
            status="CONFLICT" if any("CONFLICT" in p for p in problems) else "UNVERIFIABLE" if problems else "SUPPORTED", issues=problems))
    for code in validation.issues:
        name, evidence = None, None
        match = re.match(r"FIELD_(\d+)_", code)
        if match and int(match[1]) < len(fields):
            field = fields[int(match[1])]
            name, evidence = field.name, field.evidence
        if code.startswith("MISSING_REQUIRED_FIELD:"):
            name = code.split(":", 1)[1]
            validation.field_checks.append(FieldCheck(name=name, status="MISSING", issues=[code]))
        if code.startswith("FIELD_CONFLICT:"):
            name = code.split(":", 1)[1]
        validation.details.append(ValidationIssue(code=code, category="MISSING" if code.startswith("MISSING_") or code == "NO_EXTRACTED_FIELDS" else "INCONSISTENCY", field=name, evidence=evidence))
    if fields and not any(f.name == "professional_license" for f in fields):
        validation.details.append(ValidationIssue(code="PROFESSIONAL_LICENSE_NOT_PRESENT", category="WARNING", field="professional_license"))
    return validation


def validate_processing(content: ContentResult, classification: ClassificationResult | None,
                        extraction: ExtractionResult | None, policy: dict | None = None) -> ValidationResult:
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
            "LABORATORY_RESULT": "LABORATORY", "LABORATORY_ORDER": "LABORATORY",
        }.get(classification.document_type)
        if expected_specialty and classification.specialty not in (expected_specialty, "CARDIOPULMONARY"):
            issues.append("CLASSIFICATION_SPECIALTY_CONFLICT")
        evidence = classification.evidence
        if not evidence_supported(content, evidence):
            issues.append("CLASSIFICATION_EVIDENCE_NOT_FOUND")
    if extraction is None or not extraction.fields:
        issues.append("NO_EXTRACTED_FIELDS")
    else:
        for index, field in enumerate(extraction.fields):
            if not evidence_supported(content, field.evidence):
                issues.append(f"FIELD_{index}_EVIDENCE_NOT_FOUND")
            elif not literal_present(field.value, field.evidence.quote):
                issues.append(f"FIELD_{index}_VALUE_NOT_SUPPORTED")
            if field.unit and not literal_present(field.unit, field.evidence.quote):
                issues.append(f"FIELD_{index}_UNIT_NOT_SUPPORTED")
    if classification:
        present = {field.name for field in extraction.fields if field.value.strip()} if extraction else set()
        for group in (policy["required_groups"] if policy else REQUIRED_GROUPS.get(classification.document_type, ())):
            if not any(name in present for name in group):
                issues.append("MISSING_REQUIRED_FIELD:" + group[0])
        # Pair each repeated drug/test rather than borrowing a dose or result from another.
        paired = {"PRESCRIPTION": ("medication_name", "medication_dose", "medication_frequency"),
                  "LABORATORY_RESULT": ("test_name", "test_result")}.get(classification.document_type)
        if paired and extraction:
            relevant = [field for field in extraction.fields if field.name in paired]
            repeated = any(sum(field.name == name for field in relevant) > 1 for name in paired)
            if repeated and any(field.entity_id is None for field in relevant):
                issues.append("REPEATED_ENTITIES_NOT_GROUPED")
            for entity_id in {field.entity_id for field in relevant if field.entity_id}:
                names = {field.name for field in relevant if field.entity_id == entity_id}
                if not set(paired).issubset(names):
                    issues.append("INCOMPLETE_ENTITY:" + entity_id)
    if extraction:
        for name in ("patient_identity", "patient_name", "patient_age"):
            values = {normalized(f.value) for f in extraction.fields if f.name == name}
            if len(values) > 1:
                issues.append("FIELD_CONFLICT:" + name)
    return describe_validation(ValidationResult(valid=not issues, requires_human_review=bool(issues), issues=issues,
                              rule_version="documentary-v4"), extraction)
