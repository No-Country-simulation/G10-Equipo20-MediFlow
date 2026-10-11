"""Repair only verifiable column/heading joins, never approximate factual values."""
import re
from app.services.processing_validation import literal_present, evidence_supported


def literal_spans(value, source):
    parts = value.split()
    if not parts:
        return []
    literal = r'\s+'.join(re.escape(part) for part in parts)
    if re.fullmatch(r'[-+]?\d+(?:[.,]\d+)*', value.strip()):
        pattern = r'(?<![\w.,])' + literal + r'(?!\w|[.,]\d)'
    else:
        pattern = r'(?<!\w)' + literal + r'(?!\w)'
    return list(re.finditer(pattern, source, re.I))


def align_citations(content, extraction):
    for field in extraction.fields:
        evidence = field.evidence
        field.original_value, field.value_adjustment = None, None
        # A model may append a sentence-ending period to a literal narrative.
        # Correct only that exact case; never normalize measurements, names,
        # identity numbers, internal punctuation, or approximate word matches.
        page_text = next((p.text for p in content.pages if p.page == evidence.page), '')
        narratives = {'conclusion', 'findings', 'hallazgos', 'conclusion_estudio',
                      'discharge_diagnosis', 'follow_up', 'procedure_indication', 'certificate_purpose'}
        value = field.value.rstrip()
        if (field.name in narratives and value.endswith('.') and not value.endswith('..')
                and len(value.split()) >= 2 and value[-2:-1].isalpha()
                and literal_present(evidence.quote, page_text)
                and not literal_present(value, evidence.quote)
                and literal_present(value[:-1], evidence.quote)):
            field.original_value, field.value = field.value, value[:-1]
            field.value_adjustment = 'TERMINAL_PUNCTUATION'
        # These fields are provenance from the server, never assertions by a model.
        evidence.original_quote, evidence.match_strategy = None, None
        if evidence_supported(content, evidence) or evidence.page is None:
            continue
        # Attribution of a person/professional cannot be established by a name alone.
        if field.name.startswith(('patient_', 'professional_')) or field.name == 'priority_signal':
            continue
        if not literal_present(field.value, evidence.quote):
            continue
        if field.unit and not literal_present(field.unit, field.value):
            continue
        page = next((p for p in content.pages if p.page == evidence.page), None)
        if page is None:
            continue
        matches = literal_spans(field.value, page.text)
        pieces = [line.strip() for line in evidence.quote.splitlines() if line.strip()]
        if len(matches) != 1 or len(pieces) < 2:
            continue
        cursor, first, valid = 0, None, True
        for piece in pieces:
            spans = literal_spans(piece, page.text[cursor:])
            if not spans:
                valid = False
                break
            match = spans[0]
            if first is None:
                first = cursor + match.start()
            cursor += match.end()
        match = matches[0]
        if valid and cursor - first <= 1500 and first <= match.start() < match.end() <= cursor:
            evidence.original_quote = evidence.quote
            evidence.quote = page.text[match.start():match.end()]
            evidence.match_strategy = 'SOURCE_REANCHORED'
    return extraction
