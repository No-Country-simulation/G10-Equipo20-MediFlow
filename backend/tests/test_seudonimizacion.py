"""Paso 6: seudonimización de la ruta de texto (RN-M1, RN-M3, RN-M4).

Nombres, identificadores, fechas exactas, direcciones y teléfonos se reemplazan por
tokens antes de enviar a OpenAI. El mapa de re-identificación nunca sale de la
instalación. Las edades y los datos clínicos se conservan: el LLM los necesita.
"""
import pytest

from app.services.seudonimizacion import Seudonimizador, reidentificar, reidentificar_estructura

TEXTO_CASO_13 = (
    "Paciente: Carlos Eduardo Mendes, 52 años. CC 1.020.304.050.\n"
    "Tel: 300 123 4567. Dirección: Calle 45 # 12-34, Bogotá.\n"
    "Fecha: 03/04/2026. TC de tórax: tromboembolismo pulmonar agudo bilateral.\n"
    "Losartán 0,5 mg cada 12 h. Heparina 5.000 UI SC.\n"
    "Dr. Andrés Felipe Rojas, RM 45678. IPS Cardiovida NIT 800.197.268-4."
)


@pytest.fixture
def seudo():
    return Seudonimizador()


# --- Caso 13 ----------------------------------------------------------------


def test_caso_13_el_texto_que_sale_solo_contiene_tokens_RN_M1(seudo):
    r = seudo.seudonimizar(TEXTO_CASO_13)
    for dato in ("Carlos", "Eduardo", "Mendes", "1.020.304.050", "1020304050", "300 123 4567",
                 "Calle 45", "03/04/2026", "Andrés", "Rojas", "800.197.268-4"):
        assert dato not in r.texto, dato
    assert "[PACIENTE_1]" in r.texto
    assert "CC [ID_1]" in r.texto
    assert "[TEL_1]" in r.texto
    assert "[DIRECCION_1]" in r.texto
    assert "[FECHA_1]" in r.texto
    assert "[PROFESIONAL_1]" in r.texto
    assert "NIT [NIT_1]" in r.texto


def test_el_mapa_permite_volver_al_original_exacto(seudo):
    r = seudo.seudonimizar(TEXTO_CASO_13)
    assert reidentificar(r.texto, r.mapa) == TEXTO_CASO_13


def test_los_datos_clinicos_y_la_edad_se_conservan_RN_A4_RN_M3(seudo):
    r = seudo.seudonimizar(TEXTO_CASO_13)
    for dato in ("52 años", "tromboembolismo pulmonar agudo", "Losartán 0,5 mg", "Heparina 5.000 UI", "RM 45678"):
        assert dato in r.texto, dato


def test_el_mapa_va_de_token_a_original(seudo):
    r = seudo.seudonimizar(TEXTO_CASO_13)
    assert r.mapa["[PACIENTE_1]"] == "Carlos Eduardo Mendes"
    assert r.mapa["[ID_1]"] == "1.020.304.050"
    assert r.mapa["[NIT_1]"] == "800.197.268-4"
    assert r.mapa["[FECHA_1]"] == "03/04/2026"


# --- Consistencia y tipos de dato -----------------------------------------


def test_el_mismo_valor_recibe_el_mismo_token(seudo):
    r = seudo.seudonimizar("CC 1020304050 ... se confirma CC 1020304050 al egreso.")
    assert r.texto.count("[ID_1]") == 2
    assert "[ID_2]" not in r.texto


def test_valores_distintos_reciben_tokens_distintos(seudo):
    r = seudo.seudonimizar("Paciente: Ana Pérez. Acompañante: Sra. Luisa Gómez.")
    assert r.mapa["[PACIENTE_1]"] == "Ana Pérez"
    assert r.mapa["[PACIENTE_2]"] == "Luisa Gómez"


@pytest.mark.parametrize(
    "texto, token",
    [
        ("Tel +57 300 123 4567", "[TEL_1]"),
        ("Celular 3001234567", "[TEL_1]"),
        ("Fijo (601) 234 5678", "[TEL_1]"),
        ("Correo: carlos.mendes@example.com", "[EMAIL_1]"),
        ("Vive en Carrera 7 No. 45-12", "[DIRECCION_1]"),
        ("Vive en Cra 15 # 100-20 apto 301", "[DIRECCION_1]"),
        ("Nació el 3 de abril de 1974", "[FECHA_1]"),
        ("Ingreso 2026-04-03", "[FECHA_1]"),
        ("TI 1020304050", "[ID_1]"),
        ("C.C. No. 80197268", "[ID_1]"),
        ("Cédula de ciudadanía 80197268", "[ID_1]"),
        ("RC 1020304050", "[ID_1]"),
        ("Documento 1020304050", "[ID_1]"),
        ("Nombre del paciente: MARÍA JOSÉ LÓPEZ", "[PACIENTE_1]"),
        ("Dra. Carolina Duque", "[PROFESIONAL_1]"),
        ("Médico tratante: Juan Pablo Ríos", "[PROFESIONAL_1]"),
    ],
)
def test_detecta_cada_tipo_de_dato_personal(seudo, texto, token):
    r = seudo.seudonimizar(texto)
    assert token in r.texto, r.texto


def test_numero_largo_sin_etiqueta_tambien_se_tokeniza(seudo):
    r = seudo.seudonimizar("Identificado con 1020304050 en admisión.")
    assert "1020304050" not in r.texto
    assert "[ID_1]" in r.texto


@pytest.mark.parametrize(
    "texto",
    [
        "FR 28, SpO2 88 %, FC 118, PAS 92, Temp 37,1",
        "Plaquetas 250000, leucocitos 12500",
        "Troponina 0,45 ng/mL; BNP 1.250 pg/mL",
        "Paciente de 52 años con disnea",
        "NEWS2 total 10. Dosis 2.500 UI.",
    ],
)
def test_no_toca_valores_clinicos(seudo, texto):
    assert seudo.seudonimizar(texto).texto == texto


def test_nombres_conocidos_por_metadatos_se_tokenizan_sin_etiqueta(seudo):
    texto = "El señor Mendes refiere dolor. Carlos Eduardo Mendes ingresa por urgencias."
    r = seudo.seudonimizar(texto, nombres_conocidos=["Carlos Eduardo Mendes"])
    assert "Mendes" not in r.texto
    assert "Carlos" not in r.texto
    assert reidentificar(r.texto, r.mapa) == texto


def test_texto_vacio(seudo):
    r = seudo.seudonimizar("")
    assert r.texto == ""
    assert r.mapa == {}


# --- Re-identificación de la salida del LLM ----------------------------------


def test_reidentificar_estructura_recorre_dicts_y_listas():
    mapa = {"[PACIENTE_1]": "Carlos Eduardo Mendes", "[ID_1]": "1.020.304.050", "[FECHA_1]": "03/04/2026"}
    salida = {
        "paciente": {"nombre": "[PACIENTE_1]", "documento": {"valor": "[ID_1]"}},
        "fecha_documento": "[FECHA_1]",
        "diagnosticos": [{"texto": "TEP en [PACIENTE_1]"}],
        "edad": 52,
    }
    r = reidentificar_estructura(salida, mapa)
    assert r["paciente"]["nombre"] == "Carlos Eduardo Mendes"
    assert r["paciente"]["documento"]["valor"] == "1.020.304.050"
    assert r["fecha_documento"] == "03/04/2026"
    assert r["diagnosticos"][0]["texto"] == "TEP en Carlos Eduardo Mendes"
    assert r["edad"] == 52
    assert salida["paciente"]["nombre"] == "[PACIENTE_1]"  # no muta la entrada
