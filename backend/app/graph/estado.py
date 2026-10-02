"""Estado que viaja por el grafo. Los objetos pesados (evaluación, resultado) se
mantienen en memoria dentro de la misma transacción; lo persistente vive en la base."""
from typing import Any, TypedDict


class EstadoGrafo(TypedDict, total=False):
    documento_pk: int
    codigo_error: str | None  # motivo de rechazo decidido por validar (RN-I5)
    propuesta: dict[str, Any] | None  # propuesta del LLM ya re-identificada
    error: str | None  # motivo del fallo técnico, si lo hubo
    evaluado: Any  # app.services.evaluacion.Evaluado
    resultado: Any  # app.schemas.resultado.ResultadoTriaje
