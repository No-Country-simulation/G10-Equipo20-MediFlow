"""Fill omitted administrative fields only from an explicit signing block.

This complements LLM extraction; it does not infer who signed from an arbitrary
name, a requesting doctor, or the mention of a clinician in the narrative.
"""
import re

from app.schemas.processing import ContentResult, Evidence, ExtractedField, ExtractionResult
from app.services.patients import normalize_name

SIGNER = re.compile(
    r"^\s*(?:firma(?:\s+y\s+sello)?(?:\s+del?\s+(?:m[eé]dico|profesional)(?:\s+tratante)?)?|"
    r"m[eé]dico\s+(?:tratante|firmante|responsable)|profesional\s+firmante)\s*(?::\s*(.*))?$", re.I)
NAME = re.compile(r"^\s*(?:nombre(?:\s+(?:del?\s+)?(?:m[eé]dico|profesional))?)\s*:\s*(.+?)\s*$", re.I)
LICENSE = re.compile(r"^\s*(?:registro\s+m[eé]dico|matr[ií]cula(?:\s+profesional)?|registro\s+profesional)\s*:\s*(.+?)\s*$", re.I)
STOP = re.compile(r"^\s*(?:\d+\.\s|paciente\s*:|nombre\s+del\s+paciente|documento\s*:)", re.I)


def _valid_name(value: str) -> bool:
    words = value.split()
    return len(words) >= 2 and all(any(c.isalpha() for c in word) for word in words) and not any(c.isdigit() for c in value)


def complete_professional(content: ContentResult, extraction: ExtractionResult) -> ExtractionResult:
    candidates: dict[str, list[ExtractedField]] = {}
    licenses: dict[str, set[str]] = {}
    for page in content.pages:
        lines = page.text.splitlines()
        for index, line in enumerate(lines):
            signer = SIGNER.fullmatch(line)
            if not signer:
                continue
            name = signer.group(1)
            name_index = index
            license_value = None
            license_index = None
            for end in range(index + 1, min(index + 7, len(lines))):
                if STOP.search(lines[end]):
                    break
                found = NAME.fullmatch(lines[end])
                if found and name is None:
                    name, name_index = found.group(1), end
                found = LICENSE.fullmatch(lines[end])
                if found:
                    license_value, license_index = found.group(1), end
            if not name or not _valid_name(name):
                continue
            key = normalize_name(name)
            fields = [ExtractedField(name='professional_name', value=name, unit=None,
                evidence=Evidence(page=page.page, quote='\n'.join(lines[index:name_index + 1]).strip()))]
            if license_value:
                licenses.setdefault(key, set()).add(license_value)
                fields.append(ExtractedField(name='professional_license', value=license_value, unit=None,
                    evidence=Evidence(page=page.page, quote='\n'.join(lines[index:license_index + 1]).strip())))
            candidates.setdefault(key, fields)
    if len(candidates) != 1:
        return extraction
    key, detected = next(iter(candidates.items()))
    existing_names = {normalize_name(f.value) for f in extraction.fields if f.name == 'professional_name'}
    if existing_names and existing_names != {key}:
        return extraction
    existing_licenses = {f.value for f in extraction.fields if f.name == 'professional_license'}
    if existing_licenses and licenses.get(key) and existing_licenses != licenses[key]:
        return extraction
    present = {field.name for field in extraction.fields}
    added = [field for field in detected if field.name not in present
             and (field.name != 'professional_license' or len(licenses.get(key, ())) == 1)]
    return extraction.model_copy(update={'fields': [*extraction.fields, *added]}) if added else extraction
