from pathlib import Path
from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import Settings
from app.providers.base import DocumentProvider
from app.schemas.processing import ClassificationResult, ContentResult, ExtractionResult, ValidationResult, RoutingResult
from app.services.content import ContentReader
from app.services.errors import DocumentError
from app.services.processing_validation import validate_processing
from app.services.routing import route_classification


class ProcessingState(TypedDict):
    document_id: str
    path: Path
    format: str
    content: NotRequired[ContentResult]
    classification: NotRequired[ClassificationResult]
    extraction: NotRequired[ExtractionResult]
    validation: NotRequired[ValidationResult]
    routing: NotRequired[RoutingResult]


def build_processing_graph(provider: DocumentProvider, settings: Settings):
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
        return {"extraction": provider.extract(state["content"], state["classification"])}

    def validate(state):
        return {"validation": validate_processing(
            state["content"], state.get("classification"), state.get("extraction"),
        )}

    builder = StateGraph(ProcessingState)
    builder.add_node("ingest", ingest)
    builder.add_node("read_content", read_content)
    builder.add_node("classify", classify)
    builder.add_node("extract", extract)
    builder.add_node("validate", validate)
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
    builder.add_node("route", lambda state: {"routing": route_classification(state["classification"])})
    builder.add_conditional_edges("validate", lambda state: "route" if state["validation"].valid else END, ["route", END])
    builder.add_edge("route", END)
    return builder.compile()
