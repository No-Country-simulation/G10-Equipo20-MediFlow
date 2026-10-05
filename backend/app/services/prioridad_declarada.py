"""Prioridad que el propio documento declara en una línea ("Prioridad: urgente").

Con el LLM disponible, esa línea la lee el LLM y llega como prioridad propuesta. Con el LLM
caído no hay propuesta: esta lectura determinística ordena la cola de revisión (RN-J1, RN-P4).
Solo sube el nivel, nunca lo baja (RN-D8), y no interpreta nada clínico: lee una etiqueta.
"""
import re
import unicodedata
from dataclasses import dataclass

from app.schemas.resultado import NivelPrioridad as N

_LINEA = re.compile(r"^[ \t]*(?:prioridad(?:[ \t]+cl[ií]nica)?|nivel[ \t]+de[ \t]+urgencia)[ \t]*:[ \t]*(.+?)[ \t]*$",
                    re.IGNORECASE | re.MULTILINE)
_NIVELES = {
    "rutina": N.RUTINA, "rutinaria": N.RUTINA, "rutinario": N.RUTINA,
    "urgente": N.URGENTE,
    "critico": N.CRITICO, "critica": N.CRITICO,
}
_ORDEN = {N.RUTINA: 0, N.URGENTE: 1, N.CRITICO: 2}


@dataclass(frozen=True)
class PrioridadDeclarada:
    nivel: N
    linea: str


def _clave(valor: str) -> str:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", valor) if unicodedata.category(c) != "Mn")
    return sin_tildes.strip().rstrip(".").casefold()


def prioridad_declarada(texto: str | None) -> PrioridadDeclarada | None:
    """La declaración más alta del texto. Un valor que no es un nivel conocido se ignora."""
    mejor: PrioridadDeclarada | None = None
    for coincidencia in _LINEA.finditer(texto or ""):
        nivel = _NIVELES.get(_clave(coincidencia.group(1)))
        if nivel is not None and (mejor is None or _ORDEN[nivel] > _ORDEN[mejor.nivel]):
            mejor = PrioridadDeclarada(nivel, coincidencia.group(0).strip())
    return mejor
