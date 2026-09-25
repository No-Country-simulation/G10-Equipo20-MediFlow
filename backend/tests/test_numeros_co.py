"""Paso 4: separadores numéricos del pack Colombia (RN-C7, RN-CO10)."""
from decimal import Decimal

import pytest

from app.packs.loader import cargar_pack
from app.packs.numeros import Convencion, detectar_convencion, parsear_cantidad

PACK = cargar_pack("CO")


# --- Detección de la convención del documento -------------------------------


def test_documento_con_coma_decimal():
    texto = "Losartán 0,5 mg cada 12 horas. Heparina 5.000 UI SC."
    assert detectar_convencion(texto) is Convencion.COMA_DECIMAL


def test_documento_con_punto_decimal():
    texto = "Bisoprolol 2.5 mg al día. Enalapril 1.000 mg."
    assert detectar_convencion(texto) is Convencion.PUNTO_DECIMAL


def test_documento_mixto():
    texto = "Losartán 0,5 mg. Bisoprolol 2.5 mg."
    assert detectar_convencion(texto) is Convencion.MIXTA


def test_documento_sin_evidencia():
    texto = "Heparina 5.000 UI. Enoxaparina 60 mg."
    assert detectar_convencion(texto) is Convencion.INDETERMINADA


# --- Lecturas correctas -----------------------------------------------------


def test_caso_14_heparina_5000_UI_con_coma_decimal_en_otra_linea():
    doc = "Heparina 5.000 UI SC cada 12 h.\nLosartán 0,5 mg cada 24 h."
    c = parsear_cantidad("5.000", convencion=detectar_convencion(doc), pack=PACK)
    assert c.valor == Decimal("5000")
    assert c.ambigua is False


def test_caso_26_lectura_de_0_coma_5_mg_es_medio_miligramo_RN_C7():
    c = parsear_cantidad("0,5", convencion=Convencion.COMA_DECIMAL, pack=PACK)
    assert c.valor == Decimal("0.5")


def test_2500_UI_son_dos_mil_quinientas_RN_CO10():
    c = parsear_cantidad("2.500", convencion=Convencion.COMA_DECIMAL, pack=PACK)
    assert c.valor == Decimal("2500")
    assert c.ambigua is False


def test_miles_con_varios_grupos_nunca_es_ambiguo():
    c = parsear_cantidad("1.234.567", convencion=Convencion.INDETERMINADA, pack=PACK)
    assert c.valor == Decimal("1234567")
    assert c.ambigua is False


def test_decimal_con_dos_cifras_no_es_ambiguo():
    c = parsear_cantidad("12,5", convencion=Convencion.INDETERMINADA, pack=PACK)
    assert c.valor == Decimal("12.5")
    assert c.ambigua is False


def test_miles_y_decimal_a_la_colombiana():
    c = parsear_cantidad("1.250,75", convencion=Convencion.INDETERMINADA, pack=PACK)
    assert c.valor == Decimal("1250.75")


def test_entero_sin_separador():
    c = parsear_cantidad("60", convencion=Convencion.INDETERMINADA, pack=PACK)
    assert c.valor == Decimal("60")


def test_punto_decimal_con_una_o_dos_cifras_se_lee_como_decimal_en_doc_punto():
    c = parsear_cantidad("2.5", convencion=Convencion.PUNTO_DECIMAL, pack=PACK)
    assert c.valor == Decimal("2.5")
    assert c.ambigua is False


# --- Ambigüedades (RN-CO10) -------------------------------------------------


def test_caso_15_1000_mg_en_documento_con_punto_decimal_es_ambiguo():
    doc = "Metformina 1.000 mg. Bisoprolol 2.5 mg."
    c = parsear_cantidad("1.000", convencion=detectar_convencion(doc), pack=PACK)
    assert c.ambigua is True
    assert c.valor is None
    assert c.motivo == "dosis_ambigua"


def test_separador_con_tres_digitos_sin_confirmacion_es_ambiguo():
    c = parsear_cantidad("1.000", convencion=Convencion.INDETERMINADA, pack=PACK)
    assert c.ambigua is True


def test_coma_con_tres_digitos_sin_confirmacion_es_ambiguo():
    c = parsear_cantidad("2,500", convencion=Convencion.INDETERMINADA, pack=PACK)
    assert c.ambigua is True


def test_coma_con_tres_digitos_en_doc_coma_decimal_se_lee_decimal():
    c = parsear_cantidad("2,500", convencion=Convencion.COMA_DECIMAL, pack=PACK)
    assert c.valor == Decimal("2.500")
    assert c.ambigua is False


def test_documento_mixto_hace_ambiguo_el_separador_con_tres_digitos():
    c = parsear_cantidad("5.000", convencion=Convencion.MIXTA, pack=PACK)
    assert c.ambigua is True


def test_texto_no_numerico_es_ambiguo():
    c = parsear_cantidad("cinco mil", convencion=Convencion.COMA_DECIMAL, pack=PACK)
    assert c.ambigua is True
    assert c.valor is None


@pytest.mark.parametrize("texto", ["5.000 UI", " 0,5 mg ", "2500UI"])
def test_acepta_unidad_pegada_y_espacios(texto):
    c = parsear_cantidad(texto, convencion=Convencion.COMA_DECIMAL, pack=PACK)
    assert c.valor is not None
