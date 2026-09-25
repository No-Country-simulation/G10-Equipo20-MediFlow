"""Paso 8: NEWS2 en código, nunca en el LLM (RN-D3, RN-D4, RN-D5, RN-N1, RN-N2, RN-N4)."""
import pytest

from app.packs.loader import cargar_umbrales
from app.schemas.propuesta import SignosVitalesPropuestos as SV
from app.services.news2 import calcular_news2

U = cargar_umbrales()


def test_paciente_estable_suma_cero():
    r = calcular_news2(SV(FR=16, SpO2=97, FC=72, PAS=120, Temp=36.8, nivel_conciencia="alerta"), edad=52, umbrales=U)
    assert r.aplicable is True
    assert r.total == 0
    assert r.critico is False
    assert r.completo is True


def test_caso_1_TEP_con_signos_de_shock_es_critico_por_total():
    r = calcular_news2(SV(FR=28, SpO2=88, FC=118, PAS=92, Temp=37.1, nivel_conciencia="alerta"), edad=52, umbrales=U)
    # FR 28 -> 3, SpO2 88 -> 3, FC 118 -> 2, PAS 92 -> 2, Temp 37.1 -> 0, alerta -> 0
    assert r.total == 10
    assert r.critico is True
    assert "NEWS2_total" in r.motivos


@pytest.mark.parametrize(
    "signos, motivo",
    [
        (SV(FR=8), "FR"),
        (SV(FR=25), "FR"),
        (SV(SpO2=91), "SpO2"),
        (SV(FC=40), "FC"),
        (SV(FC=131), "FC"),
        (SV(PAS=90), "PAS"),
        (SV(nivel_conciencia="confuso"), "nivel_conciencia"),
    ],
)
def test_un_solo_parametro_en_rojo_es_critico_RN_D3(signos, motivo):
    r = calcular_news2(signos, edad=40, umbrales=U)
    assert r.critico is True
    assert motivo in r.motivos


@pytest.mark.parametrize("signos", [SV(FR=9), SV(FR=24), SV(SpO2=92), SV(FC=41), SV(FC=130), SV(PAS=91)])
def test_un_paso_fuera_del_umbral_no_es_critico_por_parametro_RN_U3(signos):
    r = calcular_news2(signos, edad=40, umbrales=U)
    assert r.critico is False


def test_total_6_no_es_critico_y_7_si_RN_U3():
    # FR 24 -> 2, SpO2 93 -> 2, FC 130 -> 2 = 6
    assert calcular_news2(SV(FR=24, SpO2=93, FC=130), edad=40, umbrales=U).critico is False
    # + Temp 38.5 -> 1 = 7
    assert calcular_news2(SV(FR=24, SpO2=93, FC=130, Temp=38.5), edad=40, umbrales=U).critico is True


def test_caso_8_SpO2_88_en_EPOC_hipercapnico_usa_escala_2_RN_D4():
    r = calcular_news2(SV(SpO2=88, FR=18, FC=80, PAS=120), edad=68, umbrales=U, epoc_hipercapnico=True)
    assert r.escala_spo2 == 2
    assert r.puntajes["SpO2"] == 0
    assert r.critico is False


def test_SpO2_88_sin_EPOC_hipercapnico_es_critico_RN_D3():
    r = calcular_news2(SV(SpO2=88, FR=18, FC=80, PAS=120), edad=68, umbrales=U)
    assert r.escala_spo2 == 1
    assert r.critico is True


def test_menor_de_16_no_aplica_NEWS2_RN_N1():
    r = calcular_news2(SV(FR=40, SpO2=85), edad=10, umbrales=U)
    assert r.aplicable is False
    assert r.motivo_no_aplicable == "menor_de_16"
    assert r.critico is False


def test_embarazo_no_aplica_NEWS2_RN_N2():
    r = calcular_news2(SV(FR=22), edad=30, umbrales=U, embarazo=True)
    assert r.aplicable is False
    assert r.motivo_no_aplicable == "embarazo"


def test_sin_edad_no_se_aplican_escalas_RN_N4():
    r = calcular_news2(SV(FR=22), edad=None, umbrales=U)
    assert r.aplicable is False
    assert r.motivo_no_aplicable == "sin_edad"


def test_sin_signos_vitales_no_hay_nada_que_evaluar():
    r = calcular_news2(SV(), edad=52, umbrales=U)
    assert r.hay_signos is False
    assert r.total is None
    assert r.critico is False


def test_signos_parciales_dan_total_parcial():
    r = calcular_news2(SV(FR=22, SpO2=95), edad=52, umbrales=U)
    assert r.completo is False
    assert r.total == 3  # FR 22 -> 2, SpO2 95 -> 1
