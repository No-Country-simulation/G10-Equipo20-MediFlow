"""Paso 8: evaluación determinística sobre la propuesta del LLM (EVALUADO).

Cubre los casos de aceptación 3, 6, 8, 9, 10, 14, 15, 18, 19, 20, 21 y 22.
"""
import pytest

from app.packs.loader import cargar_pack, cargar_umbrales
from app.schemas.resultado import EstadoIdentidad, MotivoAuditoria as M, NivelPrioridad as N
from app.services.evaluacion import evaluar
from tests.fabrica import ctx, med, propuesta, receta

PACK = cargar_pack("CO")
UMB = cargar_umbrales()


# --- Prioridad ---------------------------------------------------------------------


def test_caso_9_codigo_I26_9_eleva_a_critico_aunque_el_LLM_diga_rutina_RN_D8():
    p = propuesta(**{"extraccion.diagnosticos": [{"texto": "TEP", "cie10_sugerido": "I26.9", "cie11_sugerido": None}]})
    e = evaluar(p, ctx(), PACK, UMB)
    assert e.prioridad is N.CRITICO
    assert e.hallazgos == ["TEP_AGUDO"]
    assert any(d.regla == "RN-D8" and d.propuesta_llm == "Rutina" and d.decision == "Crítico" for d in e.historial)


def test_caso_10_solo_CIE11_tambien_es_critico_RN_CO6():
    p = propuesta(**{"extraccion.diagnosticos": [{"texto": "TEP", "cie10_sugerido": None, "cie11_sugerido": "BB00.0"}]})
    assert evaluar(p, ctx(), PACK, UMB).prioridad is N.CRITICO


def test_la_regla_nunca_baja_la_prioridad_del_LLM_RN_D8():
    p = propuesta(**{"clasificacion.nivel_prioridad_propuesto": "Urgente"})
    assert evaluar(p, ctx(), PACK, UMB).prioridad is N.URGENTE


def test_critico_por_NEWS2_sin_hallazgo_RN_D3():
    p = propuesta(**{"extraccion.signos_vitales": {"FR": 28, "SpO2": 88, "FC": 118, "PAS": 92, "Temp": 37.1, "nivel_conciencia": "alerta"}})
    e = evaluar(p, ctx(), PACK, UMB)
    assert e.prioridad is N.CRITICO
    assert e.signos_vitales.NEWS2_total == 10


def test_caso_8_EPOC_hipercapnico_con_SpO2_88_no_es_critico_RN_D4():
    p = propuesta(**{"extraccion.signos_vitales": {"FR": 18, "SpO2": 88, "FC": 80, "PAS": 120, "Temp": None, "nivel_conciencia": "alerta"},
                     "condiciones.epoc_hipercapnico": True})
    e = evaluar(p, ctx(), PACK, UMB)
    assert e.prioridad is N.RUTINA
    assert e.signos_vitales.NEWS2_total == 0


def test_triage_I_o_II_no_eleva_mientras_este_por_confirmar_RN_CO16():
    p = propuesta(**{"condiciones.triage_urgencias": "I"})
    assert evaluar(p, ctx(), PACK, UMB).prioridad is N.RUTINA


def test_critico_con_baja_confianza_alerta_y_va_a_revision_RN_D9():
    p = propuesta(**{"extraccion.diagnosticos": [{"texto": "¿TEP?", "cie10_sugerido": "I26.9", "cie11_sugerido": None}],
                     "confianzas.diagnostico_codigo": 0.6})
    e = evaluar(p, ctx(), PACK, UMB)
    assert e.prioridad is N.CRITICO
    assert e.requiere_auditoria_humana is True
    assert M.CRITICO_BAJA_CONFIANZA in e.motivos


# --- Identidad ------------------------------------------------------------------------


def test_caso_1_sin_identificador_no_bloquea_pero_retiene_HCE_RN_A4():
    e = evaluar(propuesta(), ctx(), PACK, UMB)
    assert e.identidad.estado is EstadoIdentidad.AUSENTE
    assert e.retiene_hce is True
    assert e.requiere_auditoria_humana is False


def test_caso_6_CC_invalida_con_baja_confianza_va_a_revision_con_campos_dudosos_RN_A4_RN_C3():
    p = propuesta(**{"extraccion.paciente.documento": {"tipo": "CC", "valor": "12AB45"}, "confianzas.identidad_paciente": 0.7,
                     "campos_dudosos": ["documento.valor"]})
    e = evaluar(p, ctx(), PACK, UMB)
    assert e.requiere_auditoria_humana is True
    assert M.IDENTIDAD_INVALIDA in e.motivos
    assert "documento.valor" in e.campos_dudosos and "identidad_paciente" in e.campos_dudosos


def test_caso_18_TI_con_45_anios_es_ambiguo_RN_CO2():
    p = propuesta(**{"extraccion.paciente.documento": {"tipo": "TI", "valor": "1020304050"}, "extraccion.paciente.edad": 45})
    e = evaluar(p, ctx(), PACK, UMB)
    assert e.requiere_auditoria_humana is True
    assert M.AMBIGUO in e.motivos


def test_caso_19_AS_con_TEP_alerta_y_retiene_HCE_RN_N3_RN_CO3():
    p = propuesta(**{"extraccion.paciente.documento": {"tipo": "AS", "valor": None}, "extraccion.paciente.nombre": None,
                     "extraccion.diagnosticos": [{"texto": "TEP", "cie10_sugerido": "I26.0", "cie11_sugerido": None}]})
    e = evaluar(p, ctx(), PACK, UMB)
    assert e.prioridad is N.CRITICO
    assert e.identidad.identificador_temporal.startswith("AS-TMP-")
    assert e.retiene_hce is True
    assert e.requiere_auditoria_humana is False


# --- Clasificación y campos obligatorios ---------------------------------------------------


def test_clasificacion_bajo_umbral_va_a_revision_RN_B4():
    e = evaluar(propuesta(**{"clasificacion.score_confianza": 0.849}), ctx(), PACK, UMB)
    assert M.CLASIFICACION_BAJA_CONFIANZA in e.motivos
    assert evaluar(propuesta(**{"clasificacion.score_confianza": 0.85}), ctx(), PACK, UMB).requiere_auditoria_humana is False


def test_no_clasificable_va_a_revision_RN_B4():
    e = evaluar(propuesta(**{"clasificacion.tipo": "No Clasificable"}), ctx(), PACK, UMB)
    assert M.NO_CLASIFICABLE in e.motivos


def test_dominio_otro_es_fuera_de_alcance_salvo_certificados_RN_B3():
    assert M.FUERA_DE_ALCANCE in evaluar(propuesta(**{"clasificacion.dominio": "Otro"}), ctx(), PACK, UMB).motivos
    cert = propuesta(**{"clasificacion.dominio": "Otro", "clasificacion.tipo": "Certificado Médico",
                        "extraccion.procedimientos": []})
    assert M.FUERA_DE_ALCANCE not in evaluar(cert, ctx(), PACK, UMB).motivos


def test_falta_fecha_del_documento_es_campo_obligatorio_RN_C1():
    e = evaluar(propuesta(**{"extraccion.fecha_documento": None}), ctx(), PACK, UMB)
    assert M.CAMPO_OBLIGATORIO_FALTANTE in e.motivos
    assert "fecha_documento" in e.campos_dudosos


def test_informe_sin_diagnostico_codificado_es_campo_obligatorio_RN_C1():
    e = evaluar(propuesta(**{"extraccion.diagnosticos": []}), ctx(), PACK, UMB)
    assert M.CAMPO_OBLIGATORIO_FALTANTE in e.motivos


def test_ilegible_va_a_revision_cuando_hay_umbral_RN_C5():
    umb = UMB.model_copy(deep=True)
    umb.confianza.texto_ilegible_max = 0.3
    e = evaluar(propuesta(**{"condiciones.porcentaje_ilegible": 0.5}), ctx(), PACK, umb)
    assert M.ILEGIBLE in e.motivos


def test_signos_vitales_en_menor_de_16_van_a_revision_RN_N1():
    e = evaluar(propuesta(**{"extraccion.paciente.edad": 10, "extraccion.paciente.documento": {"tipo": "TI", "valor": "1020304050"}}), ctx(), PACK, UMB)
    assert M.SIGNOS_VITALES_SIN_ESCALA in e.motivos


# --- Receta (RN-CO8, RN-CO9, RN-CO10, RN-E6) -----------------------------------------


def test_caso_2_receta_completa_es_rutina_y_no_va_a_revision():
    e = evaluar(receta([med()]), ctx(), PACK, UMB)
    assert e.prioridad is N.RUTINA
    assert e.requiere_auditoria_humana is False
    assert e.medicamentos[0].dci == "losartan"
    assert e.medicamentos[0].alto_riesgo is False


def test_caso_3_apixaban_es_alto_riesgo_RN_E6():
    e = evaluar(receta([med("Apixabán", dosis="5 mg")]), ctx(), PACK, UMB)
    assert e.medicamentos[0].alto_riesgo is True
    assert e.alto_riesgo is True
    assert e.requiere_auditoria_humana is False


def test_caso_20_receta_sin_documento_del_paciente_RN_CO8():
    e = evaluar(receta([med()], **{"extraccion.paciente.documento": {"tipo": None, "valor": None}}), ctx(), PACK, UMB)
    assert M.RECETA_INCOMPLETA_NORMA in e.motivos


def test_receta_sin_cantidad_en_letras_es_incompleta_RN_CO8():
    e = evaluar(receta([med(cantidad_letras=None)]), ctx(), PACK, UMB)
    assert M.RECETA_INCOMPLETA_NORMA in e.motivos


def test_caso_21_cantidad_30_trece_es_ambigua_RN_CO8_RN_C4():
    e = evaluar(receta([med(cantidad_numeros="30", cantidad_letras="trece")]), ctx(), PACK, UMB)
    assert M.AMBIGUO in e.motivos
    assert "medicamentos[0].cantidad" in e.campos_dudosos


def test_caso_22_morfina_sin_recetario_oficial_RN_CO9():
    e = evaluar(receta([med("morfina", dosis="10 mg", via="IV")], **{"condiciones.recetario_oficial": False}), ctx(), PACK, UMB)
    assert M.CONTROL_ESPECIAL_SIN_RECETARIO in e.motivos
    assert e.medicamentos[0].control_especial is True
    assert e.medicamentos[0].alto_riesgo is True  # opioide IV, RN-E6


def test_morfina_con_recetario_oficial_no_va_a_revision_RN_CO9():
    e = evaluar(receta([med("morfina", dosis="10 mg", via="IV")], **{"condiciones.recetario_oficial": True}), ctx(), PACK, UMB)
    assert M.CONTROL_ESPECIAL_SIN_RECETARIO not in e.motivos


def test_caso_14_heparina_5000_UI_con_coma_decimal_en_el_documento_RN_CO10():
    texto = "Heparina 5.000 UI SC cada 12 h. Losartán 0,5 mg."
    e = evaluar(receta([med("heparina", dosis="5.000 UI", via="SC"), med("losartan", dosis="0,5 mg")]), ctx(texto=texto), PACK, UMB)
    assert M.DOSIS_AMBIGUA not in e.motivos
    assert e.medicamentos[0].dosis_valor == "5000"
    assert e.medicamentos[1].dosis_valor == "0.5"


def test_caso_15_1000_mg_en_documento_con_punto_decimal_es_ambiguo_RN_CO10():
    texto = "Metformina 1.000 mg. Bisoprolol 2.5 mg."
    e = evaluar(receta([med("metformina", dosis="1.000 mg"), med("bisoprolol", dosis="2.5 mg")]), ctx(texto=texto), PACK, UMB)
    assert M.DOSIS_AMBIGUA in e.motivos
    assert "medicamentos[0].dosis" in e.campos_dudosos


def test_dosis_bajo_umbral_de_confianza_va_a_revision_RN_C3():
    e = evaluar(receta([med()], **{"confianzas.medicamento_dosis": 0.949}), ctx(), PACK, UMB)
    assert M.CAMPO_DUDOSO in e.motivos
    assert "medicamento_dosis" in e.campos_dudosos


def test_receta_con_profesional_no_identificable_RN_A8():
    p = receta([med()], **{"extraccion.profesional": {"nombre": None, "registro_profesional": None, "tipo_documento": None, "numero_documento": None}})
    assert M.PROFESIONAL_NO_IDENTIFICABLE in evaluar(p, ctx(), PACK, UMB).motivos


# --- Fechas, historial y salida ------------------------------------------------------------


def test_caso_26_fecha_se_normaliza_a_dd_mm_aaaa_RN_CO11():
    e = evaluar(propuesta(**{"extraccion.fecha_documento": "2026-04-03"}), ctx(), PACK, UMB)
    assert e.fecha_documento == "03/04/2026"


def test_fecha_imposible_en_receta_es_fecha_ambigua_RN_C8():
    e = evaluar(receta([med()], **{"extraccion.fecha_documento": "31/02/2026"}), ctx(), PACK, UMB)
    assert M.FECHA_AMBIGUA in e.motivos


def test_motivo_principal_es_el_primero_por_severidad():
    p = receta([med("morfina", cantidad_letras=None)], **{"condiciones.recetario_oficial": False, "clasificacion.score_confianza": 0.5})
    e = evaluar(p, ctx(), PACK, UMB)
    assert e.motivo_principal is e.motivos[0]
    assert e.requiere_auditoria_humana is True


def test_historial_registra_cada_regla_disparada_RN_G2():
    p = propuesta(**{"extraccion.diagnosticos": [{"texto": "TEP", "cie10_sugerido": "I26.9", "cie11_sugerido": None}]})
    e = evaluar(p, ctx(), PACK, UMB)
    reglas = {d.regla for d in e.historial}
    assert {"RN-D2", "RN-D8", "RN-A4"} <= reglas
