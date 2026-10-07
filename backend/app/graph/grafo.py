"""Grafo determinístico LangGraph (decisión 6 de la sección 2.1).

    RECIBIDO --validar--> VALIDADO --clasificar_extraer--> CLASIFICADO -> EXTRAIDO --evaluar--> EVALUADO --enrutar--> ENRUTADO
                 |                        |                                              ^                          |
                 \\-> RECHAZADO (RN-I5)    \\-- fallo --> FALLO_TECNICO --fallo_tecnico--+   corregir / transcribir |
                                                                                 |      (RN-J4)                 v
                                                      aprobar / rechazar <-- revision_humana <-- EN_REVISION_HUMANA (RN-I4)

El grafo entra por la etapa en que está el documento: RECIBIDO valida primero; VALIDADO va directo al LLM;
EN_REVISION_HUMANA espera la decisión; ENRUTADO espera las confirmaciones; FALLO_TECNICO (el worker agotó sus
intentos) entra por fallo_tecnico. En revision_humana el grafo se interrumpe
(RN-I4) y reanuda con la decisión de la persona: rechazar cierra; aprobar pasa a entrega; corregir y transcribir vuelven
a evaluar sin tocar el LLM (RN-J4). En entrega se interrumpe por cada confirmación, verificación o acuse, y cierra en
ENTREGADO cuando no queda nada pendiente: un crítico nunca sin acuse (RN-J7).
"""
from langgraph.graph import END, START, StateGraph

from app.graph.estado import EstadoGrafo


def _rama_tras_llm(estado: EstadoGrafo) -> str:
    return "fallo_tecnico" if estado.get("error") else "evaluar"


def _rama_tras_validar(estado: EstadoGrafo) -> str:
    if estado.get("error"):
        return "fallo_tecnico"
    return "rechazado" if estado.get("codigo_error") else "clasificar_extraer"


def _estado_resultado(estado: EstadoGrafo) -> str | None:
    return (estado.get("resultado") or {}).get("estado")


def _rama_tras_enrutar(estado: EstadoGrafo) -> str:
    return "revision_humana" if _estado_resultado(estado) == "EN_REVISION_HUMANA" else "entrega"


def _rama_tras_revision(estado: EstadoGrafo) -> str:
    revision = estado.get("revision")
    if revision and revision.get("reintentar"):
        return "clasificar_extraer"  # RN-P2: la persona pidió que el LLM vuelva a leer
    if revision:
        return "evaluar"
    return "entrega" if _estado_resultado(estado) == "ENRUTADO" else "fin"


def _rama_tras_entrega(estado: EstadoGrafo) -> str:
    return "fin" if _estado_resultado(estado) == "ENTREGADO" else "entrega"


def construir_grafo(orquestador, memoria=None):
    grafo = StateGraph(EstadoGrafo)
    grafo.add_node("validar", orquestador.nodo_validar)
    grafo.add_node("clasificar_extraer", orquestador.nodo_clasificar_extraer)
    grafo.add_node("evaluar", orquestador.nodo_evaluar)
    grafo.add_node("enrutar", orquestador.nodo_enrutar)
    grafo.add_node("fallo_tecnico", orquestador.nodo_fallo_tecnico)
    grafo.add_node("revision_humana", orquestador.nodo_revision_humana)
    grafo.add_node("entrega", orquestador.nodo_entrega)

    grafo.add_conditional_edges(START, orquestador.etapa_de_entrada,
                                {"validar": "validar", "clasificar_extraer": "clasificar_extraer", "revision_humana": "revision_humana",
                                 "entrega": "entrega", "fallo_tecnico": "fallo_tecnico"})
    grafo.add_conditional_edges("validar", _rama_tras_validar, {"clasificar_extraer": "clasificar_extraer", "rechazado": END, "fallo_tecnico": "fallo_tecnico"})
    grafo.add_conditional_edges("clasificar_extraer", _rama_tras_llm, {"evaluar": "evaluar", "fallo_tecnico": "fallo_tecnico"})
    grafo.add_edge("evaluar", "enrutar")  # RN-I2
    grafo.add_conditional_edges("enrutar", _rama_tras_enrutar, {"revision_humana": "revision_humana", "entrega": "entrega"})
    grafo.add_edge("fallo_tecnico", "revision_humana")  # RN-P2: a revisión humana; RN-P4: ya alertó si había hallazgo
    grafo.add_conditional_edges("revision_humana", _rama_tras_revision,
                                {"evaluar": "evaluar", "clasificar_extraer": "clasificar_extraer", "entrega": "entrega", "fin": END})
    # Enrutado es una decisión; Entregado, un hecho (sección 3.3). Cada confirmación vuelve a esperar hasta cerrar.
    grafo.add_conditional_edges("entrega", _rama_tras_entrega, {"entrega": "entrega", "fin": END})
    return grafo.compile(checkpointer=memoria)


def diagrama_mermaid() -> str:
    """Diagrama del grafo compilado, tal como existe en el código. El README lo copia entre marcadores
    y un test comprueba que coinciden: la documentación de arquitectura nunca describe un grafo distinto."""
    from unittest.mock import MagicMock  # noqa: PLC0415 - solo se necesita la forma del grafo, no un orquestador real

    lineas = ["```mermaid", "graph TD;"]
    for linea in construir_grafo(MagicMock()).get_graph().draw_mermaid().splitlines():
        texto = linea.strip()
        if "-->" in texto or ".->" in texto:  # aristas fijas, condicionales y condicionales con etiqueta
            lineas.append("    " + texto.replace("&nbsp;", ""))
    lineas.append("```")
    return "\n".join(lineas)
