from pathlib import Path
from typing import NotRequired, TypedDict
from sqlalchemy.orm import Session

from langgraph.graph import END, START, StateGraph

from app.core.config import Settings
from app.providers.base import DocumentProvider
from app.schemas.processing import (
    ClassificationResult, ContentResult, ExtractionResult, ValidationResult, RoutingResult,
    PriorityResult, QualityResult, LocalAlert,
    PatientMatch,
)
from app.services.content import ContentReader
from app.services.errors import DocumentError
from app.services.processing_validation import validate_processing
from app.services.routing import route_classification
from app.services.triage import detect_priority, calculate_quality, local_alert
from app.services.patients import assess_patient
from app.services.identity_detection import complete_identity


class ProcessingState(TypedDict):
    document_id: str
    path: Path
    format: str
    content: NotRequired[ContentResult]
    classification: NotRequired[ClassificationResult]
    extraction: NotRequired[ExtractionResult]
    validation: NotRequired[ValidationResult]
    routing: NotRequired[RoutingResult]
    priority: NotRequired[PriorityResult]
    quality: NotRequired[QualityResult]
    local_alert: NotRequired[LocalAlert | None]
    country: NotRequired[str]
    patient: NotRequired[PatientMatch]


def build_processing_graph(provider: DocumentProvider, settings: Settings, session: Session | None = None):
    reader = ContentReader(provider, settings)

    def ingest(state):
        if not state["path"].is_file():
            raise DocumentError(422, "DOCUMENT_FILE_MISSING")
        return {}

    def read_content(state):
        if state.get("content"):
            return {}
        return {"content": reader.read(state["path"], state["format"])}

    def classify(state):
        if state.get("classification"):
            return {}
        return {"classification": provider.classify(state["content"])}

    def extract(state):
        if state.get("extraction"):
            return {}
        extracted = provider.extract(state["content"], state["classification"])
        return {"extraction": complete_identity(state["content"], extracted, state.get("country", "EC"))}

    def validate(state):
        return {"validation": validate_processing(
            state["content"], state.get("classification"), state.get("extraction"),
        )}

    def assess_priority(state):
        priority = detect_priority(state["content"])
        validation = state["validation"].model_copy(deep=True)
        if priority.ambiguous:
            validation.issues.append("PRIORITY_AMBIGUOUS")
            validation.valid = False
            validation.requires_human_review = True
        return {"priority": priority, "local_alert": local_alert(priority), "validation": validation}

    def score_quality(state):
        quality = calculate_quality(state["content"], state.get("classification"),
                                    state.get("extraction"), state["validation"], settings.min_document_quality)
        validation = state["validation"].model_copy(deep=True)
        if quality.score < quality.threshold:
            validation.issues.append("LOW_DOCUMENT_QUALITY")
            validation.valid = False
            validation.requires_human_review = True
        return {"quality": quality, "validation": validation}

    def assess_patient_node(state):
        validation = state["validation"].model_copy(deep=True)
        patient = assess_patient(state.get("extraction"), state.get("country", "EC"), validation, session)
        return {"patient": patient, "validation": validation}

    builder = StateGraph(ProcessingState)
    builder.add_node("ingest", ingest)
    builder.add_node("read_content", read_content)
    builder.add_node("classify", classify)
    builder.add_node("extract", extract)
    builder.add_node("validate", validate)
    builder.add_node("assess_priority", assess_priority)
    builder.add_node("score_quality", score_quality)
    builder.add_node("assess_patient", assess_patient_node)
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "read_content")
    builder.add_conditional_edges("read_content", lambda state:
        "classify" if any(page.text.strip() for page in state["content"].pages)
        else "validate", ["classify", "validate"])
    builder.add_conditional_edges("classify", lambda state:
        "extract" if state["classification"].document_type not in ("OTHER", "UNKNOWN")
        and state["classification"].specialty not in ("OTHER", "UNKNOWN")
        else "validate", ["extract", "validate"])
    builder.add_edge("extract", "validate")
    builder.add_edge("validate", "assess_priority")
    builder.add_edge("assess_priority", "score_quality")
    builder.add_node("route", lambda state: {"routing": route_classification(state["classification"], state["priority"], session)})
    builder.add_edge("score_quality", "assess_patient")
    builder.add_conditional_edges("assess_patient", lambda state: "route" if state["validation"].valid else END, ["route", END])
    builder.add_edge("route", END)
    return builder.compile()
