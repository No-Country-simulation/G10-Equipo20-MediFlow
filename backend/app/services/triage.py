"""Deterministic documentary priority and quality signals; no clinical inference."""
import re

from app.schemas.processing import (
    ContentResult, Evidence, ExtractionResult, LocalAlert, PriorityResult,
    QualityComponents, QualityResult, ValidationResult, ClassificationResult,
)
from app.services.processing_validation import DISCHARGE_REQUIRED_FIELDS


PRIORITY_LINE = re.compile(
    r"^\s*(?:prioridad(?:\s+cl[ií]nica)?|nivel\s+de\s+urgencia)\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)
LEVELS = {
    "rutina": "ROUTINE", "rutinaria": "ROUTINE", "rutinario": "ROUTINE",
    "urgente": "URGENT", "critico": "CRITICAL", "critica": "CRITICAL",
    "crítico": "CRITICAL", "crítica": "CRITICAL",
}


def detect_priority(content: ContentResult) -> PriorityResult:
    candidates: list[tuple[str, Evidence]] = []
    invalid = False
    for page in content.pages:
        for line in page.text.splitlines():
            match = PRIORITY_LINE.fullmatch(line)
            if not match:
                continue
            value = match.group(1).strip().rstrip(".").casefold()
            level = LEVELS.get(value)
            if not level or page.uncertain:
                invalid = True
            else:
                candidates.append((level, Evidence(page=page.page, quote=line.strip())))
    if not candidates:
        return PriorityResult(level="ROUTINE", source="DEFAULT", ambiguous=invalid)
    level, evidence = candidates[0]
    return PriorityResult(level=level, source="EXPLICIT", evidence=evidence,
                          ambiguous=invalid or any(item[0] != level for item in candidates[1:]))


def calculate_quality(content: ContentResult, classification: ClassificationResult | None,
                      extraction: ExtractionResult | None, validation: ValidationResult,
                      threshold: float) -> QualityResult:
    issues = validation.issues
    readability = float(bool(content.pages) and all(page.text.strip() and not page.uncertain for page in content.pages))
    fields = extraction.fields if extraction else []
    if classification and classification.document_type == "DISCHARGE_SUMMARY":
        names = {field.name for field in fields}
        completeness = sum(name in names for name in DISCHARGE_REQUIRED_FIELDS) / len(DISCHARGE_REQUIRED_FIELDS)
    else:
        # The other report types do not yet have complete required-field contracts.
        completeness = float(bool(fields))
    checked = len(fields) + 1
    bad = {issue.split("_")[1] for issue in issues if issue.startswith("FIELD_") and
           ("EVIDENCE_NOT_FOUND" in issue or "VALUE_NOT_SUPPORTED" in issue or "UNIT_NOT_SUPPORTED" in issue)}
    evidence = max(0.0, 1 - (len(bad) + int("CLASSIFICATION_EVIDENCE_NOT_FOUND" in issues)) / checked)
    consistency = float(not any("CONFLICT" in issue or issue == "PRIORITY_AMBIGUOUS" for issue in issues))
    components = QualityComponents(readability=readability, completeness=completeness,
                                   evidence=evidence, consistency=consistency)
    score = round(0.25 * readability + 0.30 * completeness + 0.30 * evidence + 0.15 * consistency, 3)
    return QualityResult(score=score, threshold=threshold, components=components)


def local_alert(priority: PriorityResult) -> LocalAlert | None:
    if priority.level == "ROUTINE" or priority.evidence is None:
        return None
    return LocalAlert(level=priority.level, evidence=priority.evidence,
                      message="El documento declara prioridad " +
                              ("urgente" if priority.level == "URGENT" else "crítica") +
                              ". Verificar el original.")
