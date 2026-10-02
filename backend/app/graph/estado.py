"""Estado que viaja por el grafo. Es JSON puro: se guarda como checkpoint y se lee desde otro proceso
(app/graph/memoria.py). Lo persistente vive en las tablas propias; aquí solo va lo que la siguiente etapa necesita."""
from typing import Any, TypedDict


class EstadoGrafo(TypedDict, total=False):
    documento_pk: int
    codigo_error: str | None  # motivo de rechazo decidido por validar (RN-I5)
    propuesta: dict[str, Any] | None  # propuesta del LLM ya re-identificada
    error: str | None  # motivo del fallo técnico, si lo hubo
    evaluacion: dict[str, Any] | None  # resumen de evaluar: prioridad y motivos (la evaluación completa se recalcula, es determinística)
    resultado: dict[str, Any] | None  # ResultadoTriaje volcado a JSON
