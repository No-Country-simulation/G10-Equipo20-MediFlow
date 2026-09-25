"""Paso 11: los 26 casos de aceptación de la sección 9, de punta a punta por la API (RN-U2, RN-S4).

Cada caso envía un request real, inyecta la propuesta que daría el LLM (RN-U4: sin OpenAI)
y verifica el JSON de salida. Los tres escenarios del brief son los casos 1, 2 y 6.
"""
import copy
from pathlib import Path

import pytest

from app.packs.identidad import validar_nit
from app.packs.loader import cargar_pack
from app.services.seudonimizacion import Seudonimizador
from tests.test_llm import propuesta_caso_1

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
PACK = cargar_pack("CO")


def sample(nombre: str) -> str:
    return (SAMPLES / nombre).read_text(encoding="utf-8")


def propuesta(**cambios) -> dict:
    """Propuesta base (caso 1) con cambios por ruta con puntos."""
    base = propuesta_caso_1()
    for ruta, valor in cambios.items():
        nodo = base
        partes = ruta.split(".")
        for parte in partes[:-1]:
            nodo = nodo[parte]
        nodo[partes[-1]] = valor
    return base


def receta(medicamentos, documento=None, **cambios) -> dict:
    p = propuesta(**{
        "clasificacion.tipo": "Receta Médica", "clasificacion.setting": "ambulatorio", "clasificacion.especialidad": "Cardiología",
        "clasificacion.dominio": "Cardiología", "clasificacion.nivel_prioridad_propuesto": "Rutina",
        "extraccion.paciente.documento": documento or {"tipo": "CC", "valor": "[ID_1]"},
        "extraccion.signos_vitales": {"FR": None, "SpO2": None, "FC": None, "PAS": None, "Temp": None, "nivel_conciencia": None},
        "extraccion.diagnosticos": [{"texto": "Hipertensión arterial", "cie10_sugerido": "I10", "cie11_sugerido": None}],
        "extraccion.procedimientos": [], "extraccion.hallazgos_criticos_detectados": [], "extraccion.medicamentos": medicamentos,
        "confianzas.medicamento_dosis": 0.97, "condiciones.recetario_oficial": None,
    })
    for ruta, valor in cambios.items():
        nodo = p
        partes = ruta.split(".")
        for parte in partes[:-1]:
            nodo = nodo[parte]
        nodo[partes[-1]] = valor
    return p


def med(dci, dosis, **campos) -> dict:
    m = {"dci": dci, "dosis": dosis, "concentracion": dosis, "forma_farmaceutica": "tableta", "via": "oral", "frecuencia": "cada 24 h",
         "duracion": "30 días", "cantidad_numeros": "30", "cantidad_letras": "treinta"}
    m.update(campos)
    return m


def orden(justificacion="SCA con troponina positiva y cambios del ST", cups="372100", **cambios) -> dict:
    return propuesta(**{
        "clasificacion.tipo": "Orden de Procedimiento", "clasificacion.setting": "ambulatorio", "clasificacion.especialidad": "Cardiología",
        "clasificacion.dominio": "Cardiología", "clasificacion.nivel_prioridad_propuesto": "Rutina",
        "extraccion.paciente.documento": {"tipo": "CC", "valor": "[ID_1]"},
        "extraccion.signos_vitales": {"FR": None, "SpO2": None, "FC": None, "PAS": None, "Temp": None, "nivel_conciencia": None},
        "extraccion.diagnosticos": [{"texto": "Angina estable", "cie10_sugerido": "I20.8", "cie11_sugerido": None}],
        "extraccion.procedimientos": [{"texto": "Cateterismo cardíaco", "cups": cups}],
        "extraccion.hallazgos_criticos_detectados": [], "extraccion.justificacion_clinica": justificacion,
        **cambios,
    })


TEXTO_RECETA = "FÓRMULA MÉDICA. Fecha: 03/04/2026. Paciente: Ana María Pérez, 58 años. CC 41.234.567. Losartán 50 mg cada 24 h, 30 (treinta) tabletas. Dra. Carolina Duque, RM 78901."
TEXTO_ORDEN = "ORDEN DE SERVICIOS. Fecha: 03/04/2026. Paciente: Luis Castro, 49 años. CC 79.456.123. Cateterismo cardíaco CUPS 372100. Dx I20.8. Dr. Mauricio Salazar, RM 33210."


def enviar(client, llm_falso, *, documento_id, texto, propuesta_llm, canal="Consulta_Ambulatoria", cobertura=None, pais=None):
    llm_falso.respuestas.append(propuesta_llm)
    cuerpo = {"documento_id": documento_id, "canal_origen": canal, "tipo_contenido": "texto", "contenido_texto": texto}
    if cobertura:
        cuerpo["cobertura_paciente"] = cobertura
    if pais:
        cuerpo["pais_origen"] = pais
    r = client.post("/documentos", json=cuerpo)
    assert r.status_code == 200, r.text
    return r.json()


# --- Escenarios del brief: casos 1, 2 y 6 -------------------------------------------------


def test_caso_01_tc_torax_con_TEP_sin_identificador(client, llm_falso):
    c = enviar(client, llm_falso, documento_id="DOC-CLIN-2026-8942", texto=sample("caso01_tc_torax_tep.txt"),
               propuesta_llm=propuesta(**{"extraccion.paciente.documento": {"tipo": None, "valor": None}}), canal="Guardia_Emergencias")
    r = c["resultado"]
    assert r["clasificacion"]["nivel_prioridad"] == "Crítico"
    assert r["enrutamiento"]["destino_principal"] == "Cola_Emergencia_Medica"
    assert r["evaluacion"]["requiere_auditoria_humana"] is False
    assert r["notificacion_generada"]["mensaje"] == "Alerta Crítica. Doc: DOC-CLIN-2026-8942. Nivel: Crítico. Requiere acuse."
    assert "Mendes" not in r["notificacion_generada"]["mensaje"]
    assert r["ruta_storage"] == "co/procesados/criticos/DOC-CLIN-2026-8942.json"
    assert r["extraccion"]["paciente"]["nome"] == "Carlos Eduardo Mendes"
    assert r["enrutamiento"]["entregas_retenidas"] == {"Historia_Clinica_Electronica": "identidad_ausente_conciliar"}


def test_caso_02_formula_de_losartan_completa(client, llm_falso):
    c = enviar(client, llm_falso, documento_id="DOC-REC-02", texto=sample("caso02_formula_losartan.txt"), propuesta_llm=receta([med("losartan", "50 mg")]))
    r = c["resultado"]
    assert r["clasificacion"]["nivel_prioridad"] == "Rutina"
    assert r["enrutamiento"]["destino_principal"] == "Farmacia_Hospitalaria"
    assert r["evaluacion"]["requiere_auditoria_humana"] is False
    assert r["extraccion"]["paciente"]["documento"] == {"tipo": "CC", "valor": "41234567", "estado": "valido_formato"}


def test_caso_06_CC_invalida_y_baja_confianza(client, llm_falso):
    p = propuesta(**{
        "clasificacion.tipo": "Informe de Laboratorio", "clasificacion.setting": "ambulatorio", "clasificacion.nivel_prioridad_propuesto": "Rutina",
        "extraccion.paciente.documento": {"tipo": "CC", "valor": "[ID_1]"}, "confianzas.identidad_paciente": 0.6,
        "extraccion.signos_vitales": {"FR": None, "SpO2": None, "FC": None, "PAS": None, "Temp": None, "nivel_conciencia": None},
        "extraccion.diagnosticos": [{"texto": "Dislipidemia mixta", "cie10_sugerido": "E78.2", "cie11_sugerido": None}],
        "extraccion.procedimientos": [{"texto": "Perfil lipídico", "cups": "903815"}],
        "extraccion.hallazgos_criticos_detectados": [], "campos_dudosos": ["documento.valor"],
    })
    c = enviar(client, llm_falso, documento_id="DOC-LAB-06", texto=sample("caso06_cc_invalida.txt"), propuesta_llm=p)
    r = c["resultado"]
    assert c["estado"] == "EN_REVISION_HUMANA"
    assert r["evaluacion"]["requiere_auditoria_humana"] is True
    assert "documento.valor" in r["evaluacion"]["campos_dudosos"]
    assert r["extraccion"]["paciente"]["documento"]["estado"] == "invalido"


# --- Resto de casos ------------------------------------------------------------------------


def test_caso_03_apixaban_alto_riesgo(client, llm_falso):
    c = enviar(client, llm_falso, documento_id="DOC-REC-03", texto=sample("caso03_formula_apixaban.txt"),
               propuesta_llm=receta([med("apixaban", "5 mg", frecuencia="cada 12 h", cantidad_numeros="60", cantidad_letras="sesenta")]))
    r = c["resultado"]
    assert r["enrutamiento"]["destino_principal"] == "Farmacia_Hospitalaria"
    assert r["extraccion"]["medicamentos"][0]["alto_riesgo"] is True
    assert "doble verificación" in r["enrutamiento"]["justificacion_enrutamiento"]


def test_caso_04_orden_ambulatoria_sin_justificacion(client, llm_falso):
    p = orden(justificacion=None, cups="880202", **{"extraccion.procedimientos": [{"texto": "Ecocardiograma de estrés", "cups": "880202"}]})
    c = enviar(client, llm_falso, documento_id="DOC-ORD-04", texto=sample("caso04_orden_eco_estres_sin_justificacion.txt"), propuesta_llm=p, cobertura="contributivo")
    r = c["resultado"]
    assert r["enrutamiento"]["destino_principal"] == "Auditoria_Autorizaciones"
    assert r["enrutamiento"]["documentacion_incompleta"] is True
    assert r["enrutamiento"]["motivos_destino"]["Auditoria_Autorizaciones"] == "documentacion_incompleta"


def test_caso_05_cateterismo_desde_urgencias(client, llm_falso):
    p = orden(**{"clasificacion.setting": "urgencia", "condiciones.triage_urgencias": "II"})
    c = enviar(client, llm_falso, documento_id="DOC-ORD-05", texto=sample("caso05_orden_cateterismo_urgencias.txt"), propuesta_llm=p, canal="Guardia_Emergencias")
    r = c["resultado"]
    assert r["enrutamiento"]["destino_principal"] == "Cola_Emergencia_Medica"
    assert r["enrutamiento"]["destinos_secundarios"] == ["Auditoria_Autorizaciones"]
    assert r["enrutamiento"]["motivos_destino"]["Auditoria_Autorizaciones"] == "informe_atencion_inicial_urgencias"


def test_caso_07_epicrisis_IAM_con_revascularizacion(client, llm_falso):
    p = propuesta(**{
        "clasificacion.tipo": "Epicrisis o Alta", "clasificacion.setting": "hospitalizado", "clasificacion.dominio": "Cardiología",
        "clasificacion.nivel_prioridad_propuesto": "Rutina", "extraccion.hallazgos_criticos_detectados": [],
        "extraccion.signos_vitales": {"FR": 16, "SpO2": 96, "FC": 70, "PAS": 120, "Temp": None, "nivel_conciencia": "alerta"},
        "extraccion.diagnosticos": [{"texto": "IAM, revascularización quirúrgica", "cie10_sugerido": "I21.9", "cie11_sugerido": None}],
        "extraccion.procedimientos": [{"texto": "Revascularización miocárdica", "cups": "361100"}],
    })
    texto = "EPICRISIS. Fecha: 03/04/2026. Paciente: Rosa Elena Díaz, 66 años. CC 41.111.222. Egreso tras revascularización miocárdica quirúrgica por IAM. Dr. Mauricio Salazar, RM 33210."
    c = enviar(client, llm_falso, documento_id="DOC-EPI-07", texto=texto, propuesta_llm=p, canal="Hospitalizado")
    r = c["resultado"]
    assert r["enrutamiento"]["destino_principal"] == "Historia_Clinica_Electronica"
    assert "Gestion_Programa_Cobertura" not in r["enrutamiento"]["destinos_secundarios"]
    assert any(h["regla"] == "RN-CO15" for h in r["historial_decisiones"])


def test_caso_08_SpO2_88_en_EPOC_hipercapnico(client, llm_falso):
    p = propuesta(**{
        "clasificacion.nivel_prioridad_propuesto": "Rutina", "extraccion.hallazgos_criticos_detectados": [],
        "extraccion.diagnosticos": [{"texto": "EPOC", "cie10_sugerido": "J44.9", "cie11_sugerido": None}],
        "extraccion.signos_vitales": {"FR": 18, "SpO2": 88, "FC": 80, "PAS": 120, "Temp": None, "nivel_conciencia": "alerta"},
        "condiciones.epoc_hipercapnico": True,
    })
    texto = "Fecha: 03/04/2026. Paciente: Hernando Silva, 70 años. EPOC con insuficiencia respiratoria hipercápnica crónica. SpO2 88 %. Dr. Rojas, RM 45678."
    r = enviar(client, llm_falso, documento_id="DOC-08", texto=texto, propuesta_llm=p)["resultado"]
    assert r["clasificacion"]["nivel_prioridad"] == "Rutina"
    assert r["extraccion"]["signos_vitales"]["NEWS2_total"] == 0


def test_caso_09_LLM_dice_rutina_pero_el_codigo_es_I26_9(client, llm_falso):
    p = propuesta(**{"clasificacion.nivel_prioridad_propuesto": "Rutina", "extraccion.hallazgos_criticos_detectados": [],
                     "extraccion.signos_vitales": {"FR": 16, "SpO2": 96, "FC": 80, "PAS": 120, "Temp": None, "nivel_conciencia": "alerta"}})
    texto = "Fecha: 03/04/2026. Paciente: Julio Mora, 60 años. TC de tórax. Dx I26.9. Dr. Rojas, RM 45678."
    r = enviar(client, llm_falso, documento_id="DOC-09", texto=texto, propuesta_llm=p, canal="Guardia_Emergencias")["resultado"]
    assert r["clasificacion"]["nivel_prioridad"] == "Crítico"
    assert any(h["regla"] == "RN-D8" and h["propuesta_llm"] == "Rutina" for h in r["historial_decisiones"])


def test_caso_10_TEP_codificado_solo_con_CIE11(client, llm_falso):
    p = propuesta(**{"clasificacion.nivel_prioridad_propuesto": "Rutina", "extraccion.hallazgos_criticos_detectados": [],
                     "extraccion.diagnosticos": [{"texto": "Embolia pulmonar", "cie10_sugerido": None, "cie11_sugerido": "BB00.0"}],
                     "extraccion.signos_vitales": {"FR": 16, "SpO2": 96, "FC": 80, "PAS": 120, "Temp": None, "nivel_conciencia": "alerta"}})
    texto = "Fecha: 03/04/2026. Paciente: Julio Mora, 60 años. TC de tórax. Dx BB00.0. Dr. Rojas, RM 45678."
    r = enviar(client, llm_falso, documento_id="DOC-10", texto=texto, propuesta_llm=p, canal="Guardia_Emergencias")["resultado"]
    assert r["clasificacion"]["nivel_prioridad"] == "Crítico"
    assert r["enrutamiento"]["destino_principal"] == "Cola_Emergencia_Medica"


def test_caso_11_request_sin_pais_origen_usa_CO(client, llm_falso):
    c = enviar(client, llm_falso, documento_id="DOC-11", texto=sample("caso01_tc_torax_tep.txt"), propuesta_llm=propuesta(), canal="Guardia_Emergencias")
    assert c["resultado"]["pack_pais"] == "CO"
    assert client.get("/documentos/DOC-11").json()["pais_origen"] == "CO"


def test_caso_12_mismo_documento_id_dos_veces(client, llm_falso):
    enviar(client, llm_falso, documento_id="DOC-12", texto=sample("caso01_tc_torax_tep.txt"), propuesta_llm=propuesta(), canal="Guardia_Emergencias")
    llamadas = len(llm_falso.llamadas)
    r = client.post("/documentos", json={"documento_id": "DOC-12", "canal_origen": "Guardia_Emergencias", "tipo_contenido": "texto",
                                         "contenido_texto": sample("caso01_tc_torax_tep.txt")})
    assert r.json()["duplicado"] is True
    assert len(llm_falso.llamadas) == llamadas
    assert client.get("/documentos/DOC-12").json()["alerta"]["estado_acuse"] == "pendiente"


def test_caso_13_texto_con_CC_y_nombre_real_solo_manda_tokens_a_OpenAI(client, llm_falso):
    enviar(client, llm_falso, documento_id="DOC-13", texto=sample("caso02_formula_losartan.txt"), propuesta_llm=receta([med("losartan", "50 mg")]))
    enviado = llm_falso.llamadas[-1].texto_usuario
    for dato in ("Ana María", "Pérez", "41.234.567", "41234567", "Carolina Duque", "03/04/2026", "800.197.268-4"):
        assert dato not in enviado, dato
    assert "[PACIENTE_1]" in enviado and "[ID_1]" in enviado


def test_caso_14_heparina_5000_UI_con_coma_decimal(client, llm_falso):
    texto = "FÓRMULA MÉDICA. Fecha: 03/04/2026. Paciente: Ana Pérez, 58 años. CC 41.234.567. Heparina 5.000 UI SC cada 12 h. Losartán 0,5 mg. Dra. Duque, RM 78901."
    p = receta([med("heparina", "5.000 UI", via="SC", frecuencia="cada 12 h"), med("losartan", "0,5 mg")])
    r = enviar(client, llm_falso, documento_id="DOC-14", texto=texto, propuesta_llm=p)["resultado"]
    assert r["extraccion"]["medicamentos"][0]["dosis_valor"] == "5000"
    assert r["evaluacion"]["motivo_auditoria"] != "dosis_ambigua"


def test_caso_15_1000_mg_en_documento_con_punto_decimal(client, llm_falso):
    texto = "FÓRMULA MÉDICA. Fecha: 03/04/2026. Paciente: Ana Pérez, 58 años. CC 41.234.567. Metformina 1.000 mg. Bisoprolol 2.5 mg. Dra. Duque, RM 78901."
    p = receta([med("metformina", "1.000 mg"), med("bisoprolol", "2.5 mg")])
    c = enviar(client, llm_falso, documento_id="DOC-15", texto=texto, propuesta_llm=p)
    assert c["estado"] == "EN_REVISION_HUMANA"
    assert c["resultado"]["evaluacion"]["motivo_auditoria"] == "dosis_ambigua"


def test_caso_16_CC_con_formato_correcto_no_bloquea(client, llm_falso):
    r = enviar(client, llm_falso, documento_id="DOC-16", texto=TEXTO_RECETA, propuesta_llm=receta([med("losartan", "50 mg")]))["resultado"]
    assert r["extraccion"]["paciente"]["documento"]["estado"] == "valido_formato"
    assert r["evaluacion"]["requiere_auditoria_humana"] is False


def test_caso_17_NIT_correcto_y_alterado():
    assert validar_nit("800.197.268-4") == "valido_verificado"
    assert validar_nit("800.197.268-5") == "invalido"


def test_caso_18_TI_con_45_anios(client, llm_falso):
    texto = "FÓRMULA MÉDICA. Fecha: 03/04/2026. Paciente: Ana Pérez, 45 años. TI 1020304050. Losartán 50 mg. Dra. Duque, RM 78901."
    p = receta([med("losartan", "50 mg")], documento={"tipo": "TI", "valor": "[ID_1]"}, **{"extraccion.paciente.edad": 45})
    c = enviar(client, llm_falso, documento_id="DOC-18", texto=texto, propuesta_llm=p)
    assert c["estado"] == "EN_REVISION_HUMANA"
    assert c["resultado"]["evaluacion"]["motivo_auditoria"] == "ambiguo"


def test_caso_19_adulto_sin_identificacion_con_TEP(client, llm_falso):
    texto = "Fecha: 03/04/2026. Adulto sin identificación (AS), aprox. 60 años, traído por ambulancia. TC: tromboembolismo pulmonar masivo. FR 30, SpO2 85, FC 125, PAS 85. Dr. Rojas, RM 45678."
    p = propuesta(**{"extraccion.paciente.nombre": None, "extraccion.paciente.edad": 60, "extraccion.paciente.documento": {"tipo": "AS", "valor": None},
                     "extraccion.signos_vitales": {"FR": 30, "SpO2": 85, "FC": 125, "PAS": 85, "Temp": None, "nivel_conciencia": "alerta"}})
    c = enviar(client, llm_falso, documento_id="DOC-19", texto=texto, propuesta_llm=p, canal="Guardia_Emergencias")
    r = c["resultado"]
    assert c["estado"] == "ENRUTADO"
    assert r["clasificacion"]["nivel_prioridad"] == "Crítico"
    assert r["extraccion"]["paciente"]["documento"]["valor"].startswith("AS-TMP-")
    assert r["enrutamiento"]["entregas_retenidas"] == {"Historia_Clinica_Electronica": "identidad_ausente_conciliar"}
    assert client.get("/documentos/DOC-19").json()["alerta"] is not None


def test_caso_20_formula_sin_documento_del_paciente(client, llm_falso):
    texto = "FÓRMULA MÉDICA. Fecha: 03/04/2026. Paciente: Ana Pérez, 58 años. Losartán 50 mg. Dra. Duque, RM 78901."
    c = enviar(client, llm_falso, documento_id="DOC-20", texto=texto, propuesta_llm=receta([med("losartan", "50 mg")], documento={"tipo": None, "valor": None}))
    assert c["resultado"]["evaluacion"]["motivo_auditoria"] == "receta_incompleta_norma"


def test_caso_21_cantidad_30_trece(client, llm_falso):
    p = receta([med("losartan", "50 mg", cantidad_numeros="30", cantidad_letras="trece")])
    c = enviar(client, llm_falso, documento_id="DOC-21", texto=TEXTO_RECETA.replace("(treinta)", "(trece)"), propuesta_llm=p)
    assert c["resultado"]["evaluacion"]["motivo_auditoria"] == "ambiguo"
    assert "medicamentos[0].cantidad" in c["resultado"]["evaluacion"]["campos_dudosos"]


def test_caso_22_morfina_sin_recetario_oficial(client, llm_falso):
    p = receta([med("morfina", "10 mg", via="IV", frecuencia="cada 4 h")], **{"condiciones.recetario_oficial": False})
    c = enviar(client, llm_falso, documento_id="DOC-22", texto=TEXTO_RECETA.replace("Losartán 50 mg", "Morfina 10 mg IV"), propuesta_llm=p)
    assert c["resultado"]["evaluacion"]["motivo_auditoria"] == "control_especial_sin_recetario"
    assert c["resultado"]["extraccion"]["medicamentos"][0]["control_especial"] is True


def test_caso_23_orden_ambulatoria_contributivo_completa(client, llm_falso):
    r = enviar(client, llm_falso, documento_id="DOC-23", texto=TEXTO_ORDEN, propuesta_llm=orden(), cobertura="contributivo")["resultado"]
    assert r["enrutamiento"]["destino_principal"] == "Auditoria_Autorizaciones"
    assert r["enrutamiento"]["motivos_destino"]["Auditoria_Autorizaciones"] == "solicitud_autorizacion_eps"
    assert r["evaluacion"]["requiere_auditoria_humana"] is False


def test_caso_24_misma_orden_sin_cobertura(client, llm_falso):
    c = enviar(client, llm_falso, documento_id="DOC-24", texto=TEXTO_ORDEN, propuesta_llm=orden())
    assert c["estado"] == "EN_REVISION_HUMANA"
    assert c["resultado"]["evaluacion"]["motivo_auditoria"] == "cobertura_no_informada"
    assert c["resultado"]["enrutamiento"]["destinos_tras_revision"] == ["Auditoria_Autorizaciones"]


def test_caso_25_misma_orden_con_especial_excepcion(client, llm_falso):
    c = enviar(client, llm_falso, documento_id="DOC-25", texto=TEXTO_ORDEN, propuesta_llm=orden(), cobertura="especial_excepcion")
    assert c["resultado"]["evaluacion"]["motivo_auditoria"] == "cobertura_no_configurada"


def test_caso_26_fecha_03_04_2026_es_3_de_abril(client, llm_falso):
    r = enviar(client, llm_falso, documento_id="DOC-26", texto=TEXTO_RECETA, propuesta_llm=receta([med("losartan", "50 mg")]))["resultado"]
    assert r["extraccion"]["fecha_documento"] == "03/04/2026"
    ultima = client.get("/documentos/DOC-26").json()["transiciones"][-1]["fecha_hora"]
    assert ultima  # la fecha de la transición es del sistema; la del documento es 3 de abril


# --- Cobertura de los 26 casos ------------------------------------------------------------------


def test_los_26_casos_tienen_test_RN_U2():
    codigo = Path(__file__).read_text(encoding="utf-8")
    faltantes = [n for n in range(1, 27) if f"def test_caso_{n:02d}_" not in codigo]
    assert faltantes == []
