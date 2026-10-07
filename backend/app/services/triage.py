"""Deterministic documentary priority and quality signals; no clinical inference."""
import re

from app.schemas.processing import (
    ContentResult, Evidence, ExtractionResult, LocalAlert, PriorityResult,
    QualityComponents, QualityResult, ValidationResult, ClassificationResult,
)
from app.core.document_catalog import completeness


PRIORITY_LINE = re.compile(
    r"^\s*(?:prioridad(?:\s+cl[ií]nica)?|prioridade|priority|nivel\s+de\s+urgencia)\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)
LEVELS = {
    "rutina": "ROUTINE", "rutinaria": "ROUTINE", "rutinario": "ROUTINE",
    "urgente": "URGENT", "critico": "CRITICAL", "critica": "CRITICAL",
    "crítico": "CRITICAL", "crítica": "CRITICAL",
    "routine": "ROUTINE", "rotina": "ROUTINE", "urgent": "URGENT", "critical": "CRITICAL",
}


def detect_priority(content: ContentResult) -> PriorityResult:
    candidates: list[tuple[str, Evidence]] = []
    invalid = False
    from app.services.documentary_policy import annotate_text_evidence
    historical = re.compile(r"\b(?:antecedente|antecedentes|hist[oó]ri[ac]\w*|pr[eé]vi[oa]|anterior|pasad[oa]|ayer|descartad[oa]|resuelt[oa]|sospecha|posible|sin|no|niega|n[aã]o|history|historical|previous|suspected|possible|not|ruled\s+out)\b", re.I)
    urgent = re.compile(r"\b(?:atenci[oó]n\s+(?:inmediata|urgente)|evaluaci[oó]n\s+urgente|derivaci[oó]n\s+urgente|aten[cç][aã]o\s+imediata|avalia[cç][aã]o\s+urgente|immediate\s+attention|urgent\s+evaluation)\b", re.I)
    critical = re.compile(r"\b(?:(?:hallazgo|resultado|achado)\s+cr[ií]tico|critical\s+(?:finding|result))\b", re.I)
    for page in content.pages:
        for line in page.text.splitlines():
            match = PRIORITY_LINE.fullmatch(line)
            if not match:
                # Explicit action/result statements only; no diagnosis-based inference.
                signal = False
                for clause in re.split(r"[;.!?]\s*", line):
                    if critical.search(clause) or urgent.search(clause):
                        signal = True
                        if historical.search(clause):
                            continue
                        if page.uncertain:
                            invalid = True
                        else:
                            candidates.append(("CRITICAL" if critical.search(clause) else "URGENT", annotate_text_evidence(content, Evidence(page=page.page, quote=clause.strip()))))
                if not signal and re.search(r"\b(?:urgente|cr[ií]tico|emergencia)\b", line, re.I) and not historical.search(line):
                    # A label/channel alone is not a priority declaration.
                    if not re.match(r"\s*(?:canal|servicio|[aá]rea|ingreso|guardia)\s*:", line, re.I) and line.strip().casefold() not in ("urgencias", "emergencias"):
                        invalid = True
                continue
            value = match.group(1).strip().rstrip(".").casefold()
            level = LEVELS.get(value)
            if not level or page.uncertain:
                invalid = True
            else:
                candidates.append((level, annotate_text_evidence(content, Evidence(page=page.page, quote=line.strip()))))
    if not candidates:
        return PriorityResult(level="ROUTINE", source="DEFAULT", ambiguous=invalid, rule_version="evidence-priority-v2",
                              reason="REVIEW_CONTEXT_REQUIRED" if invalid else "NO_CONFIRMED_PRIORITY")
    level, evidence = max(candidates, key=lambda item: {"ROUTINE": 0, "URGENT": 1, "CRITICAL": 2}[item[0]])
    return PriorityResult(level=level, source="EXPLICIT", evidence=evidence,
                          ambiguous=invalid or len({item[0] for item in candidates}) > 1,
                          rule_version="evidence-priority-v2", reason="EXPLICIT_DOCUMENT_STATEMENT")


def calculate_quality(content: ContentResult, classification: ClassificationResult | None,
                      extraction: ExtractionResult | None, validation: ValidationResult,
                      threshold: float, policy: dict | None = None) -> QualityResult:
    issues = validation.issues
    readability = float(bool(content.pages) and all(page.text.strip() and not page.uncertain for page in content.pages))
    fields = extraction.fields if extraction else []
    coverage = completeness(classification.document_type if classification else None, fields)
    if policy:
        groups = policy["required_groups"]
        names = {f.name for f in fields if f.value.strip()}
        coverage = sum(any(n in names for n in group) for group in groups) / len(groups) if groups else 0
    checked = len(fields) + 1
    bad = {issue.split("_")[1] for issue in issues if issue.startswith("FIELD_") and
           ("EVIDENCE_NOT_FOUND" in issue or "VALUE_NOT_SUPPORTED" in issue or "UNIT_NOT_SUPPORTED" in issue)}
    evidence = max(0.0, 1 - (len(bad) + int("CLASSIFICATION_EVIDENCE_NOT_FOUND" in issues)) / checked)
    consistency = float(not any("CONFLICT" in issue or issue == "PRIORITY_AMBIGUOUS"
                               or issue.startswith("INCOMPLETE_ENTITY:") or issue == "REPEATED_ENTITIES_NOT_GROUPED"
                               for issue in issues))
    components = QualityComponents(readability=readability, completeness=coverage,
                                   evidence=evidence, consistency=consistency)
    weights = policy["weights"] if policy else {"readability": .25, "completeness": .30, "evidence": .30, "consistency": .15}
    score = round(sum(weights[key] * value for key, value in components.model_dump().items()), 3)
    return QualityResult(score=score, threshold=policy["threshold"] if policy else threshold, components=components,
                         rule_version="document-quality-v3", policy=policy)


def local_alert(priority: PriorityResult) -> LocalAlert | None:
    if priority.level == "ROUTINE" or priority.evidence is None:
        return None
    return LocalAlert(level=priority.level, evidence=priority.evidence,
                      message="El documento declara prioridad " +
                              ("urgente" if priority.level == "URGENT" else "crítica") +
                              ". Verificar el original.")
