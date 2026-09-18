from typing import NotRequired, TypedDict


class DocumentState(TypedDict):
    """Referencia tecnica a un documento; no contiene informacion clinica."""

    document_id: str
    initialized: NotRequired[bool]
