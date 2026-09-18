from app.graph.state import DocumentState


def initialize_document(state: DocumentState) -> dict[str, bool]:
    """Marca la inicializacion sin modificar la entrada ni llamar servicios."""
    return {"initialized": True}
