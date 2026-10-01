"""Prioridad declarada por el documento: una etiqueta leída sin LLM (RN-P4), que solo sube el nivel (RN-D8)."""
import pytest

from app.schemas.resultado import NivelPrioridad as N
from app.services.prioridad_declarada import prioridad_declarada


@pytest.mark.parametrize("linea, nivel", [
    ("Prioridad: urgente", N.URGENTE),
    ("PRIORIDAD CLÍNICA: Crítica.", N.CRITICO),
    ("  Nivel de urgencia : crítico", N.CRITICO),
    ("Prioridad: Rutinaria", N.RUTINA),
])
def test_lee_la_etiqueta_sin_distinguir_mayusculas_ni_tildes(linea, nivel):
    declarada = prioridad_declarada(f"Informe de control.\n{linea}\nDr. Rojas")
    assert declarada.nivel is nivel
    assert declarada.linea == linea.strip()


def test_sin_etiqueta_o_con_un_valor_desconocido_no_declara_nada():
    assert prioridad_declarada("Control de hipertensión. Losartán 50 mg.") is None
    assert prioridad_declarada("Prioridad: alta") is None
    assert prioridad_declarada("") is None
    assert prioridad_declarada(None) is None


def test_la_etiqueta_debe_ocupar_su_linea():
    assert prioridad_declarada("Se discute si la prioridad: urgente aplica o no en este caso") is None


def test_ante_dos_declaraciones_distintas_gana_la_mas_alta():
    declarada = prioridad_declarada("Prioridad: rutina\nHallazgos...\nPrioridad: urgente")
    assert declarada.nivel is N.URGENTE
    assert declarada.linea == "Prioridad: urgente"
