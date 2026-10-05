"""Paso 4: identidad del paciente y NIT en el pack Colombia (RN-A4, RN-CO1 a RN-CO4)."""
import pytest

from app.packs.identidad import validar_identidad_paciente, validar_nit
from app.packs.loader import cargar_pack
from app.schemas.resultado import EstadoIdentidad

PACK = cargar_pack("CO")


# --- Casos de aceptación ----------------------------------------------------


def test_caso_16_CC_correcta_es_valido_formato_y_no_bloquea():
    r = validar_identidad_paciente("CC", "1020304050", edad=30, pack=PACK)
    assert r.estado is EstadoIdentidad.VALIDO_FORMATO
    assert r.bloquea_triaje is False
    assert r.retiene_hce is False


def test_caso_6_CC_con_letras_es_invalido():
    r = validar_identidad_paciente("CC", "12AB45", edad=30, pack=PACK)
    assert r.estado is EstadoIdentidad.INVALIDO
    assert r.motivo == "identidad_invalida"


def test_caso_18_TI_con_45_anios_es_ambiguo_RN_CO2():
    r = validar_identidad_paciente("TI", "1020304050", edad=45, pack=PACK)
    assert r.estado is EstadoIdentidad.VALIDO_FORMATO
    assert r.coherente_con_edad is False
    assert r.motivo == "ambiguo"
    assert r.requiere_revision_humana is True


def test_caso_19_AS_recibe_identificador_temporal_RN_CO3():
    r = validar_identidad_paciente("AS", None, edad=60, pack=PACK)
    assert r.identificador_temporal.startswith("AS-TMP-")
    assert r.bloquea_triaje is False
    assert r.retiene_hce is True
    assert r.requiere_revision_humana is False


def test_MS_recibe_identificador_temporal_con_secuencia_RN_CO3():
    r = validar_identidad_paciente("MS", None, edad=5, pack=PACK, secuencia=7)
    assert r.identificador_temporal == "MS-TMP-0007"


# --- RN-A4: los cuatro estados ----------------------------------------------


def test_ausente_retiene_HCE_pero_no_bloquea_RN_A4():
    r = validar_identidad_paciente(None, None, edad=52, pack=PACK)
    assert r.estado is EstadoIdentidad.AUSENTE
    assert r.bloquea_triaje is False
    assert r.retiene_hce is True
    assert r.requiere_revision_humana is False


def test_en_CO_nunca_hay_valido_verificado_para_personas_RN_CO1():
    r = validar_identidad_paciente("CC", "80197268", edad=40, pack=PACK)
    assert r.estado is EstadoIdentidad.VALIDO_FORMATO


def test_invalido_va_a_revision_humana_RN_A4():
    r = validar_identidad_paciente("CC", "12", edad=40, pack=PACK)
    assert r.estado is EstadoIdentidad.INVALIDO
    assert r.requiere_revision_humana is True


def test_tipo_desconocido_es_invalido():
    r = validar_identidad_paciente("RUN", "12345678-9", edad=40, pack=PACK)
    assert r.estado is EstadoIdentidad.INVALIDO


# --- RN-CO1: formatos por tipo ----------------------------------------------


@pytest.mark.parametrize(
    "tipo, valor, edad",
    [
        ("CC", "123456", 30),  # mínimo 6 dígitos
        ("CC", "1234567890", 30),  # máximo 10
        ("TI", "1020304050", 12),  # 10 dígitos
        ("TI", "10203040506", 12),  # 11 dígitos
        ("RC", "1020304050", 3),  # NUIP de 10 dígitos
        ("RC", "AB12345678", 3),  # serial alfanumérico
        ("PA", "AB123456", 30),
        ("PA", "A" * 16, 30),
    ],
)
def test_formatos_validos_RN_CO1(tipo, valor, edad):
    assert validar_identidad_paciente(tipo, valor, edad=edad, pack=PACK).estado is EstadoIdentidad.VALIDO_FORMATO


@pytest.mark.parametrize(
    "tipo, valor, edad",
    [
        ("CC", "12345", 30),  # menos de 6
        ("CC", "12345678901", 30),  # más de 10
        ("TI", "123456789", 12),  # 9 dígitos
        ("PA", "A" * 17, 30),
    ],
)
def test_formatos_invalidos_RN_CO1(tipo, valor, edad):
    assert validar_identidad_paciente(tipo, valor, edad=edad, pack=PACK).estado is EstadoIdentidad.INVALIDO


def test_tipo_por_confirmar_se_acepta_y_baja_score_RN_CO1():
    r = validar_identidad_paciente("CE", "123456", edad=30, pack=PACK)
    assert r.estado is EstadoIdentidad.VALIDO_FORMATO
    assert r.formato_por_confirmar is True
    assert r.requiere_revision_humana is False


def test_CD_SC_DE_solo_presencia_RN_CO1():
    r = validar_identidad_paciente("SC", "cualquier-cosa-2026", edad=30, pack=PACK)
    assert r.estado is EstadoIdentidad.VALIDO_FORMATO


def test_valor_con_puntos_y_espacios_se_normaliza():
    r = validar_identidad_paciente("CC", " 1.020.304.050 ", edad=30, pack=PACK)
    assert r.estado is EstadoIdentidad.VALIDO_FORMATO
    assert r.valor_normalizado == "1020304050"


# --- RN-CO2: coherencia documento-edad --------------------------------------


@pytest.mark.parametrize(
    "tipo, edad",
    [("RC", 0), ("RC", 6), ("RC", 7), ("TI", 6), ("TI", 7), ("TI", 17), ("TI", 18), ("CC", 17), ("CC", 18), ("CC", 90)],
)
def test_edades_coherentes_con_tolerancia_de_un_anio_RN_CO2(tipo, edad):
    valor = {"RC": "1020304050", "TI": "1020304050", "CC": "1020304050"}[tipo]
    assert validar_identidad_paciente(tipo, valor, edad=edad, pack=PACK).coherente_con_edad is True


@pytest.mark.parametrize("tipo, edad", [("RC", 8), ("TI", 5), ("TI", 19), ("CC", 12), ("CC", 16)])
def test_edades_incoherentes_RN_CO2(tipo, edad):
    r = validar_identidad_paciente(tipo, "1020304050", edad=edad, pack=PACK)
    assert r.coherente_con_edad is False
    assert r.requiere_revision_humana is True


def test_extranjeros_no_se_evaluan_por_edad_RN_CO2():
    r = validar_identidad_paciente("PA", "AB123456", edad=5, pack=PACK)
    assert r.coherente_con_edad is None
    assert r.requiere_revision_humana is False


def test_sin_edad_no_se_evalua_coherencia_RN_N4():
    r = validar_identidad_paciente("TI", "1020304050", edad=None, pack=PACK)
    assert r.coherente_con_edad is None


# --- RN-CO4: NIT con dígito verificador (módulo 11 DIAN) --------------------


def test_caso_17_NIT_correcto_y_alterado_RN_CO4():
    assert validar_nit("800.197.268-4") is EstadoIdentidad.VALIDO_VERIFICADO
    assert validar_nit("800.197.268-5") is EstadoIdentidad.INVALIDO


@pytest.mark.parametrize("nit", ["800197268-4", "8001972684", "800.197.268-4", "860.002.964-4"])
def test_NIT_acepta_formatos_con_y_sin_separadores(nit):
    assert validar_nit(nit) is EstadoIdentidad.VALIDO_VERIFICADO


@pytest.mark.parametrize("nit", ["", "abc", "12-3", "800197268"])
def test_NIT_sin_digito_o_mal_formado_es_invalido(nit):
    assert validar_nit(nit) is EstadoIdentidad.INVALIDO
