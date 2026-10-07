from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, model_validator
from app.core.document_catalog import REQUIRED_GROUPS
from app.models.execution import DocumentPolicy


class PolicyInput(BaseModel):
    expected_version: int = Field(ge=1)
    required_groups: list[list[str]] = Field(min_length=1, max_length=40)
    weights: dict[str, float]
    threshold: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def check_weights(self):
        if set(self.weights) != {"readability", "completeness", "evidence", "consistency"}:
            raise ValueError("Four documentary weights are required")
        if any(not 0 < v <= 1 for v in self.weights.values()) or abs(sum(self.weights.values()) - 1) > 1e-6:
            raise ValueError("Positive weights must sum to 1")
        if any(not group or len(group) != len(set(group)) for group in self.required_groups):
            raise ValueError("Required groups must contain distinct field names")
        return self


def load_policy(session: Session | None, kind: str | None, threshold: float) -> dict:
    row = session.get(DocumentPolicy, kind) if session is not None and kind in REQUIRED_GROUPS else None
    return {"document_type": kind, "version": row.version if row else 0,
            **(row.configuration if row else {"required_groups": REQUIRED_GROUPS.get(kind, ()),
                "weights": {"readability": .25, "completeness": .30, "evidence": .30, "consistency": .15},
                "threshold": threshold})}


def annotate_text_evidence(content, evidence):
    if evidence is None or not content.pages or content.pages[0].page is not None:
        return evidence
    source = content.pages[0].text
    start = source.find(evidence.quote)
    return evidence.model_copy(update={"page": None, "start": start if start >= 0 else None,
                                        "end": start + len(evidence.quote) if start >= 0 else None})


def clinical_projection(extraction):
    from app.schemas.processing import ClinicalData, MedicationData, LaboratoryData, ProcedureData
    result = ClinicalData()
    if not extraction:
        return result
    groups = {}
    for index, field in enumerate(extraction.fields):
        if field.name.startswith("patient_"):
            key = field.name.removeprefix("patient_")
            if key in type(result.patient).model_fields and getattr(result.patient, key) is None:
                setattr(result.patient, key, field)
        if field.name.startswith("professional_"):
            key = field.name.removeprefix("professional_")
            if key in type(result.professional).model_fields and getattr(result.professional, key) is None:
                setattr(result.professional, key, field)
        for prefix, names, model, target in (
            ("medication_", {"name", "dose", "frequency", "route", "duration", "concentration"}, MedicationData, result.medications),
            ("test_", {"name", "result"}, LaboratoryData, result.tests),
            ("procedure_", {"indication"}, ProcedureData, result.procedures),
        ):
            if not (field.name.startswith(prefix) or prefix == "test_" and field.name == "reference_range"
                    or prefix == "procedure_" and field.name == "requested_procedure"):
                continue
            key = "name" if field.name == "requested_procedure" else "reference_range" if field.name == "reference_range" else field.name.removeprefix(prefix)
            if key not in names and not (prefix == "test_" and key == "reference_range") and not (prefix == "procedure_" and field.name == "requested_procedure"):
                continue
            group_key = (prefix, field.entity_id or "single")
            item = groups.get(group_key)
            if item is None or getattr(item, key) is not None:
                item = model(entity_id=field.entity_id)
                target.append(item)
                groups[group_key] = item
            setattr(item, key, field)
    return result
