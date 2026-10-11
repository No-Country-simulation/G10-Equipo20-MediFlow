"""Conservative literal fallback for labeled patient IDs in extracted text."""
import re

from app.schemas.processing import ContentResult, Evidence, ExtractedField, ExtractionResult
from app.services.patients import validate_identity

LABEL = re.compile(
    r"(?:c[eé]dula(?:\s+de\s+(?:identidad|ciudadan[ií]a))?|"
    r"documento\s+nacional\s+de\s+identidad|n[uú]mero\s+de\s+documento|"
    r"n[uú]mero\s+de\s+identificaci[oó]n|identificaci[oó]n(?:\s+del\s+paciente)?|"
    r"\bdocumento\b|"
    r"\bD\.?N\.?I\.?\b|\bCUIL\b|\bRUN\b|\bRUT\b|\bCPF\b|\bCURP\b|\bNUIP\b|\bC\.?I\.?\b|\bC\.?C\.?\b)", re.IGNORECASE)
TOKEN = re.compile(r"(?:[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d|[VE]-?\d{6,8}|\d(?:[\d. \t-]{0,20}[0-9K])?(?:[A-Z]{1,2})?)(?![A-Za-z0-9])", re.IGNORECASE)


def _value_after_label(payload: str, country: str) -> str | None:
    payload = payload.lstrip(" \t:#.-")
    # A generic label may precede the national type: Documento / CC / number.
    typed = LABEL.match(payload)
    number_at = typed.end() if typed else 0
    suffix = payload[number_at:].lstrip(" \t:#.-")
    match = TOKEN.match(suffix)
    if match is None:
        return None
    number_start = len(payload) - len(suffix)
    raw = payload[:number_start + match.end()].strip()
    return match.group().strip() if validate_identity(country, raw) else None


def detect_labeled_identity(content: ContentResult, country: str) -> ExtractedField | None:
    candidates: dict[tuple[str, str], tuple[int | None, str, str]] = {}
    for page in content.pages:
        lines = page.text.splitlines()
        for index, line in enumerate(lines):
            for label in LABEL.finditer(line):
                # Only inspect the value immediately following this label. A
                # document/HC reference elsewhere on the line is never an ID.
                payload = line[label.end():].strip(" \t:#.-")
                quote = line.strip()
                if not payload:
                    for following_index in range(index + 1, min(index + 3, len(lines))):
                        if lines[following_index].strip():
                            payload = lines[following_index].strip()
                            quote = "\n".join(lines[index:following_index + 1]).strip()
                            break
                # Preserve a national type when validating, so a foreign type
                # cannot be accepted just because its digits fit this country.
                generic = label.group().casefold().startswith(("documento", "número", "numero", "identifica"))
                raw = _value_after_label(payload if generic else label.group() + " " + payload, country)
                if raw:
                    identity = validate_identity(country, raw)
                    candidates.setdefault(identity, (page.page, quote, raw))
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
