from langgraph.graph import END, START, StateGraph

from app.graph.nodes.initialize_document import initialize_document
from app.graph.state import DocumentState


def build_document_graph():
    """Construye un grafo en memoria, sin LLM ni persistencia."""
    builder = StateGraph(DocumentState)
    builder.add_node("initialize_document", initialize_document)
    builder.add_edge(START, "initialize_document")
    builder.add_edge("initialize_document", END)
    return builder.compile()
