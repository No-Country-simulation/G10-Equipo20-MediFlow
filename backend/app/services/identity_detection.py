"""Conservative literal fallback for labeled patient IDs in extracted text."""
import re

from app.schemas.processing import ContentResult, Evidence, ExtractedField, ExtractionResult
from app.services.patients import validate_identity

LABEL = re.compile(
    r"(?:c[eé]dula(?:\s+de\s+(?:identidad|ciudadan[ií]a))?|"
    r"documento\s+nacional\s+de\s+identidad|n[uú]mero\s+de\s+documento|"
    r"n[uú]mero\s+de\s+identificaci[oó]n|identificaci[oó]n(?:\s+del\s+paciente)?|"
    r"\bDNI\b|\bRUN\b|\bRUT\b|\bCPF\b|\bCURP\b|\bCI\b|\bCC\b)", re.IGNORECASE)
TOKEN = re.compile(r"(?<![A-Za-z0-9])(?:[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d|[VE]-?\d{6,8}|\d[\d.\s-]{4,16}[0-9K])(?![A-Za-z0-9])", re.IGNORECASE)


def detect_labeled_identity(content: ContentResult, country: str) -> ExtractedField | None:
    candidates: dict[tuple[str, str], tuple[int, str, str]] = {}
    for page in content.pages:
        lines = page.text.splitlines()
        for index, line in enumerate(lines):
            if not LABEL.search(line):
                continue
            # A field may be laid out in the next row. Keep the number on its own
            # literal line for the evidence check; never use arbitrary nearby IDs.
            next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
            if not (next_line[:1].isdigit() or LABEL.search(next_line)):
                next_line = ""
            for candidate_line in (line, next_line):
                for match in TOKEN.finditer(candidate_line):
                    raw = match.group().strip()
                    identity = validate_identity(country, raw)
                    if identity:
                        candidates[(identity[0], identity[1])] = (page.page, candidate_line.strip(), raw)
                if candidates:
                    break
    if len(candidates) != 1:
        return None
    page, quote, raw = next(iter(candidates.values()))
    return ExtractedField(name="patient_identity", value=raw, unit=None,
                          evidence=Evidence(page=page, quote=quote))


def complete_identity(content: ContentResult, extraction: ExtractionResult, country: str) -> ExtractionResult:
    if any(field.name == "patient_identity" for field in extraction.fields):
        return extraction
    detected = detect_labeled_identity(content, country)
    return extraction.model_copy(update={"fields": [*extraction.fields, detected]}) if detected else extraction
