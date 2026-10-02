"""Contrato del grafo LangGraph con el ciclo de vida de la sección 3 (decisión 6 de la sección 2.1).

El grafo es la implementación del ciclo de vida: sus nodos y aristas se fijan aquí para que ningún
cambio salte una etapa (RN-I2) ni deje al README contando un grafo que ya no existe. Un cambio del
ciclo de vida exige cambiar primero este test (RN-U6).
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.graph.grafo import construir_grafo, diagrama_mermaid

README = Path(__file__).resolve().parents[2] / "README.md"
INICIO, FIN = "<!-- grafo:inicio -->", "<!-- grafo:fin -->"


def _grafo():
    return construir_grafo(MagicMock()).get_graph()


def test_nodos_del_grafo_son_las_etapas_de_la_seccion_3():
    nodos = set(_grafo().nodes) - {"__start__", "__end__"}
    assert nodos == {"validar", "clasificar_extraer", "evaluar", "enrutar", "fallo_tecnico"}


def test_aristas_no_saltan_etapas_RN_I2():
    aristas = {(e.source, e.target) for e in _grafo().edges}
    assert aristas == {
        ("__start__", "validar"),  # RECIBIDO entra por la validación sin LLM (sección 3.3)
        ("__start__", "clasificar_extraer"),  # un documento ya VALIDADO entra por su etapa
        ("validar", "clasificar_extraer"),
        ("validar", "__end__"),  # RECHAZADO: único rechazo del sistema (RN-I5)
        ("validar", "fallo_tecnico"),  # el original no se pudo leer
        ("clasificar_extraer", "evaluar"),
        ("clasificar_extraer", "fallo_tecnico"),  # RN-P2, RN-P3
        ("evaluar", "enrutar"),
        ("enrutar", "__end__"),
        ("fallo_tecnico", "__end__"),  # RN-P4: a revisión humana, con la detección determinística
    }
    # RN-I2: nada llega a enrutar sin pasar por evaluar.
    assert all(origen == "evaluar" for origen, destino in aristas if destino == "enrutar")


def test_el_grafo_entra_por_la_etapa_en_que_esta_el_documento():
    entradas = {e.target for e in _grafo().edges if e.source == "__start__"}
    assert entradas == {"validar", "clasificar_extraer"}


def test_la_decision_tras_el_llm_es_condicional():
    condicionales = {(e.source, e.target) for e in _grafo().edges if e.conditional}
    assert condicionales >= {("clasificar_extraer", "evaluar"), ("clasificar_extraer", "fallo_tecnico")}
    assert ("evaluar", "enrutar") not in condicionales  # RN-I2: evaluar siempre sigue a enrutar


def test_el_readme_muestra_el_grafo_compilado_real():
    if not README.exists():
        pytest.skip("el README no se versiona; el bloque se comprueba donde existe")
    texto = README.read_text(encoding="utf-8")
    assert INICIO in texto and FIN in texto, "el README necesita el bloque del grafo entre los marcadores"
    bloque = texto.split(INICIO, 1)[1].split(FIN, 1)[0].strip()
    assert bloque == diagrama_mermaid().strip()
