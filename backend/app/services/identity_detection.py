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
# Role markers apply to any document type, regardless of the ID's country.
PATIENT_ROLE = re.compile(r"^\s*(?:(?:datos|identificaci[oó]n|documento|nombre)\s+(?:del?\s+)?)?"
                          r"(?:paciente|patient|pacient[ea]|usuario)\b", re.I)
OTHER_ROLE = re.compile(r"^\s*(?:firma|firmante|sello|m[eé]dico|doctor|dra?\.|profesional|"
                        r"rethus|registro\s+(?:m[eé]dico|profesional)|acompa[ñn]ante|"
                        r"acudiente|responsable|tutor|representante)\b|^\s*dra?\.(?=\s|$)|"
                        r"\b(?:del?\s+(?:m[eé]dico|profesional|acudiente|representante)|rethus)\b", re.I)


def _patient_context(lines: list[str], index: int) -> bool:
    # Section ownership persists until another explicit role begins. Document
    # titles and mentions of clinicians in narrative text do not own an ID.
    role = None
    for line in lines[:index + 1]:
        if PATIENT_ROLE.search(line):
            role = 'patient'
        elif OTHER_ROLE.search(line):
            role = 'other'
    if OTHER_ROLE.search(lines[index]) and not PATIENT_ROLE.search(lines[index]):
        return False
    if role == 'patient':
        return True
    # Column extraction can put DOCUMENTO / number immediately before PACIENTE.
    for line in lines[index + 1:index + 5]:
        if PATIENT_ROLE.search(line):
            return True
        if OTHER_ROLE.search(line):
            return False
    return role != 'other'


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


def detect_labeled_identities(content: ContentResult, country: str) -> list[ExtractedField]:
    candidates: dict[tuple[str, str], tuple[int | None, str, str]] = {}
    for page in content.pages:
        lines = page.text.splitlines()
        for index, line in enumerate(lines):
            if not _patient_context(lines, index):
                continue
            for label in LABEL.finditer(line):
                # Only inspect the value immediately following this label. A
                # document/HC reference elsewhere on the line is never an ID.
                payload = line[label.end():].strip(" \t:#.-")
                quote = line.strip()
                if not payload:
                    for following_index in range(index + 1, min(index + 6, len(lines))):
                        following = lines[following_index].strip()
                        if not following:
                            continue
                        payload = (payload + " " + following).strip()
                        quote = "\n".join(lines[index:following_index + 1]).strip()
                        if not LABEL.fullmatch(following.rstrip(".:# ")):
                            break
                # Preserve a national type when validating, so a foreign type
                # cannot be accepted just because its digits fit this country.
                generic = label.group().casefold().startswith(("documento", "número", "numero", "identifica"))
                raw = _value_after_label(payload if generic else label.group() + " " + payload, country)
                if raw:
                    identity = validate_identity(country, raw)
                    candidates.setdefault(identity, (page.page, quote, raw))
    return [ExtractedField(name="patient_identity", value=raw, unit=None,
                           evidence=Evidence(page=page, quote=quote))
            for page, quote, raw in candidates.values()]


def detect_labeled_identity(content: ContentResult, country: str) -> ExtractedField | None:
    candidates = detect_labeled_identities(content, country)
    return candidates[0] if len(candidates) == 1 else None


def complete_identity(content: ContentResult, extraction: ExtractionResult, country: str) -> ExtractionResult:
    detected = detect_labeled_identities(content, country)
    existing = {validate_identity(country, field.value) for field in extraction.fields
                if field.name == "patient_identity"}
    # Preserve disagreements for validation instead of silently choosing an ID
    # or presenting multiple patient candidates as if no ID had been printed.
    added = [field for field in detected if validate_identity(country, field.value) not in existing]
    return extraction.model_copy(update={"fields": [*extraction.fields, *added]}) if added else extraction
