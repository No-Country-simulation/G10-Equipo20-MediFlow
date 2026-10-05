"""Paso 4: el pack de país es configuración, no código (sección 4)."""
import pytest

from app.packs.loader import cargar_pack, cargar_umbrales


def test_pack_CO_se_carga_desde_yaml():
    pack = cargar_pack("CO")
    assert pack.pais == "CO"
    assert pack.formato.separador_decimal == ","
    assert pack.formato.separador_miles == "."
    assert pack.formato.formato_fecha == "dd/mm/aaaa"


def test_pack_desconocido_falla_explicito_RN_S2():
    with pytest.raises(FileNotFoundError):
        cargar_pack("XX")


def test_pack_CO_declara_tipos_de_documento_RN_CO1():
    pack = cargar_pack("CO")
    codigos = set(pack.identidad_paciente.tipos)
    assert {"CC", "TI", "RC", "CE", "PA", "PT", "CN", "CD", "SC", "DE", "MS", "AS"} <= codigos
    assert pack.identidad_paciente.tipos["CC"].estado == "verificado_en_parte"
    assert pack.identidad_paciente.tipos["CE"].estado == "por_confirmar"
    assert pack.identidad_paciente.digito_verificador_personas is False


def test_pack_CO_declara_rangos_de_edad_RN_CO2():
    rangos = cargar_pack("CO").identidad_paciente.rangos_edad
    assert rangos["RC"].edad_max == 6
    assert (rangos["TI"].edad_min, rangos["TI"].edad_max) == (7, 17)
    assert rangos["CC"].edad_min == 18
    assert cargar_pack("CO").identidad_paciente.tolerancia_edad_anios == 1


def test_pack_CO_profesional_sin_jurisdiccion_RN_CO5():
    prof = cargar_pack("CO").identidad_profesional
    assert prof.registro == "ReTHUS"
    assert prof.exige_jurisdiccion is False
    assert prof.verificacion_en_linea.disponible is True


def test_pack_CO_terminologia_dual_y_tabla_critica_RN_CO6_RN_D1():
    pack = cargar_pack("CO")
    assert pack.terminologia.diagnosticos == "dual"
    conceptos = {h.concepto for h in pack.hallazgos_criticos}
    assert conceptos == {
        "TEP_AGUDO", "IAM_STEMI", "DISECCION_AORTICA", "NEUMOTORAX_TENSION",
        "TAPONAMIENTO_CARDIACO", "INSUF_RESPIRATORIA_AGUDA", "ARRITMIA_MALIGNA", "EDEMA_AGUDO_PULMON",
    }
    tep = next(h for h in pack.hallazgos_criticos if h.concepto == "TEP_AGUDO")
    assert {"I26.0", "I26.9"} <= set(tep.cie10)
    assert "BB00.0" in tep.cie11
    assert any("tromboembolismo pulmonar" in s for s in tep.sinonimos)


def test_pack_CO_medicamentos_alto_riesgo_y_control_especial_RN_E6_RN_CO9():
    pack = cargar_pack("CO")
    assert "apixaban" in pack.medicamentos.alto_riesgo
    assert "heparina" in pack.medicamentos.alto_riesgo
    assert {"morfina", "hidromorfona", "fentanilo", "metadona"} <= set(pack.medicamentos.control_especial)


def test_pack_CO_coberturas_con_estado_RN_CO12():
    cob = cargar_pack("CO").coberturas
    assert cob["contributivo"].modelo == "asegurador"
    assert cob["contributivo"].estado == "verificado"
    assert cob["especial_excepcion"].estado == "por_confirmar"
    assert cob["soat"].estado == "por_confirmar"


def test_pack_CO_programas_inactivos_mientras_por_confirmar_RN_E11():
    prog = cargar_pack("CO").programas_cobertura
    assert prog["mipres"].estado == "por_confirmar"
    assert prog["alto_costo"].estado == "por_confirmar"
    assert prog["mipres"].activo is False


def test_pack_CO_vocabulario_regional_RN_C6():
    voc = cargar_pack("CO").vocabulario
    assert "fórmula médica" in voc["Receta Médica"]
    assert "urgencias" in voc["Guardia_Emergencias"]


def test_pack_CO_retencion_15_anios_RN_CO18():
    assert cargar_pack("CO").retencion.anios == 15


def test_umbrales_se_cargan_desde_configuracion_seccion_7():
    u = cargar_umbrales()
    assert u.confianza.clasificacion == 0.85
    assert u.confianza.identidad_paciente == 0.95
    assert u.confianza.medicamento_dosis == 0.95
    assert u.confianza.diagnostico_codigo == 0.90
    assert u.confianza.profesional == 0.85
    assert u.confianza.resto == 0.80
    assert u.tiempos.comunicacion_critico_min == 60
    assert u.tiempos.escalamiento_sin_acuse_min == 15


def test_umbrales_NEWS2_no_son_configurables_RN_D5():
    u = cargar_umbrales()
    assert u.news2.configurable is False
    assert (u.news2.fr_bajo, u.news2.fr_alto) == (8, 25)
    assert u.news2.spo2_bajo == 91
    assert (u.news2.fc_bajo, u.news2.fc_alto) == (40, 131)
    assert u.news2.pas_bajo == 90
    assert u.news2.total_critico == 7
    assert u.news2.edad_minima == 16


def test_umbral_de_confianza_caso_borde_RN_U3():
    u = cargar_umbrales()
    assert u.supera("medicamento_dosis", 0.950) is True
    assert u.supera("medicamento_dosis", 0.949) is False
    assert u.supera("clasificacion", 0.85) is True
    assert u.supera("clasificacion", 0.8499) is False
