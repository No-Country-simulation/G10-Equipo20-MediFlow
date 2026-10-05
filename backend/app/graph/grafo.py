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
