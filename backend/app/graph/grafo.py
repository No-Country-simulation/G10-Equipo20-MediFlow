"""Grafo determinístico LangGraph (decisión 6 de la sección 2.1).

    VALIDADO --clasificar_extraer--> CLASIFICADO -> EXTRAIDO --evaluar--> EVALUADO --enrutar--> ENRUTADO
                    |                                                                        \\-> EN_REVISION_HUMANA
                    \\-- fallo --> FALLO_TECNICO --fallo_tecnico--> EN_REVISION_HUMANA (RN-P2, RN-P4)
"""
from langgraph.graph import END, START, StateGraph

from app.graph.estado import EstadoGrafo


def _rama_tras_llm(estado: EstadoGrafo) -> str:
    return "fallo_tecnico" if estado.get("error") else "evaluar"


def construir_grafo(orquestador):
    grafo = StateGraph(EstadoGrafo)
    grafo.add_node("clasificar_extraer", orquestador.nodo_clasificar_extraer)
    grafo.add_node("evaluar", orquestador.nodo_evaluar)
    grafo.add_node("enrutar", orquestador.nodo_enrutar)
    grafo.add_node("fallo_tecnico", orquestador.nodo_fallo_tecnico)

    grafo.add_edge(START, "clasificar_extraer")
    grafo.add_conditional_edges("clasificar_extraer", _rama_tras_llm, {"evaluar": "evaluar", "fallo_tecnico": "fallo_tecnico"})
    grafo.add_edge("evaluar", "enrutar")
    grafo.add_edge("enrutar", END)
    grafo.add_edge("fallo_tecnico", END)
    return grafo.compile()


def diagrama_mermaid() -> str:
    """Diagrama del grafo compilado, tal como existe en el código. El README lo copia entre marcadores
    y un test comprueba que coinciden: la documentación de arquitectura nunca describe un grafo distinto."""
    from unittest.mock import MagicMock  # noqa: PLC0415 - solo se necesita la forma del grafo, no un orquestador real

    lineas = ["```mermaid", "graph TD;"]
    for linea in construir_grafo(MagicMock()).get_graph().draw_mermaid().splitlines():
        texto = linea.strip()
        if "-->" in texto or "-.->" in texto:
            lineas.append("    " + texto)
    lineas.append("```")
    return "\n".join(lineas)
