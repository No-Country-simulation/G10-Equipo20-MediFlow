"""Fase D: métricas calculadas desde el historial (RN-R1), aviso por tasa de corrección (RN-R4),
versiones por documento (RN-R5), costo en tokens (RN-T3) y sin datos del paciente (RN-M4)."""
import pytest

from tests.test_aceptacion import med, propuesta, receta, sample, TEXTO_RECETA
from tests.test_api_farmacia_autorizaciones import enviar

AUDITOR = {"usuario": "aud.ana", "rol": "auditor_clinico"}


def poblar(client, llm_falso):
    """Tres documentos: una receta automática, una a revisión por campo dudoso (corregida) y un TEP crítico acusado."""
    enviar(client, llm_falso, "REC-OK", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    enviar(client, llm_falso, "REC-DUD", TEXTO_RECETA.replace("Losartán", "Enalapril"),
           receta([med("enalapril", "10 mg")], **{"confianzas.medicamento_dosis": 0.90}))
    assert client.get("/documentos/REC-DUD").json()["estado"] == "EN_REVISION_HUMANA"
    r = client.post("/revision/REC-DUD/resolver", json={**AUDITOR, "accion": "corregir", "motivo": "dosis verificada contra el original",
                                                        "correcciones": {"extraccion.medicamentos.0.dosis": "20 mg", "confianzas.medicamento_dosis": 0.99}})
    assert r.status_code == 200, r.text
    enviar(client, llm_falso, "TEP-1", sample("caso01_tc_torax_tep.txt"),
           propuesta(**{"extraccion.paciente.documento": {"tipo": None, "valor": None}}), canal="Guardia_Emergencias")
    assert client.post("/alertas/TEP-1/acuse", json={"usuario": "jefe.rojas"}).status_code == 200


def test_metricas_RN_R1_se_calculan_del_historial(client, llm_falso):
    poblar(client, llm_falso)
    r = client.get("/metricas", params={"dias": 30})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["periodo_dias"] == 30 and m["documentos"] == 3
    # tasa de automatización: los que nunca pasaron por revisión humana sobre los procesados
    assert m["tasa_automatizacion"] == pytest.approx(2 / 3, abs=0.01)
    # porcentaje a revisión por motivo
    assert m["revision_por_motivo"]["campo_dudoso"]["n"] == 1
    assert m["revision_por_motivo"]["campo_dudoso"]["porcentaje"] == pytest.approx(1 / 3, abs=0.01)
    # tiempo por etapa (segundos promedio entre transiciones)
    assert "RECIBIDO→VALIDADO" in m["tiempo_por_etapa_s"]
    assert m["tiempo_por_etapa_s"]["EN_REVISION_HUMANA→RESUELTO"] >= 0
    # tiempo hasta el acuse en críticos
    acuse = m["acuse_criticos"]
    assert acuse["emitidas"] == 1 and acuse["acusadas"] == 1 and acuse["pendientes"] == 0
    assert acuse["minutos_promedio"] >= 0 and acuse["dentro_de_plazo"] == 1 and acuse["plazo_min"] == 15
    # RN-M4: nunca datos del paciente
    assert "Pérez" not in r.text and "Mendes" not in r.text


def test_metricas_RN_R4_tasa_de_correccion_por_campo_avisa_y_propone_subir_el_umbral(client, llm_falso):
    poblar(client, llm_falso)
    m = client.get("/metricas").json()
    por_campo = {c["campo"]: c for c in m["correccion_por_campo"]}
    dosis = por_campo["extraccion.medicamentos.*.dosis"]
    assert dosis["correcciones"] == 1 and dosis["documentos_revisados"] == 1 and dosis["tasa"] == 1.0
    assert dosis["umbral_relacionado"] == "confianza.medicamento_dosis" and dosis["supera_limite"] is True
    assert m["limite_correccion_campo"] == 0.10
    aviso = next(a for a in m["avisos"] if a["campo"] == "extraccion.medicamentos.*.dosis")
    assert aviso["regla"] == "RN-R4" and "confianza.medicamento_dosis" in aviso["propuesta"] and aviso["umbral_actual"] == 0.95
    assert aviso["umbral_propuesto"] > 0.95


def test_metricas_falsos_negativos_criticos_son_los_que_un_humano_subio_a_critico(client, llm_falso):
    poblar(client, llm_falso)
    enviar(client, llm_falso, "REC-FN", TEXTO_RECETA.replace("Losartán", "Amiodarona"),
           receta([med("amiodarona", "200 mg")], **{"confianzas.medicamento_dosis": 0.90}))
    r = client.post("/revision/REC-FN/resolver", json={**AUDITOR, "accion": "corregir", "motivo": "QT prolongado en el texto",
                                                       "correcciones": {"nivel_prioridad": "Crítico", "confianzas.medicamento_dosis": 0.99}})
    assert r.status_code == 200, r.text
    fn = client.get("/metricas").json()["falsos_negativos_criticos"]
    assert fn["n"] == 1 and fn["documentos"] == ["REC-FN"]
    assert fn["criticos_totales"] == 2  # TEP-1 detectado por el sistema + REC-FN subido por una persona
    assert fn["tasa"] == pytest.approx(0.5)


def test_metricas_RN_R5_y_RN_T3_versiones_y_tokens_por_documento(client, llm_falso):
    poblar(client, llm_falso)
    m = client.get("/metricas").json()
    assert m["versiones"]["modelo_llm"] == {"falso": 3}
    assert m["versiones"]["version_prompt"] == {"triaje_v1": 3}
    assert m["versiones"]["version_reglas"] == {"8": 3}
    assert list(m["versiones"]["pack"]) and m["tokens"]["entrada"] == 300 and m["tokens"]["salida"] == 150


def test_metricas_sin_documentos_no_dividen_por_cero(client):
    m = client.get("/metricas").json()
    assert m["documentos"] == 0 and m["tasa_automatizacion"] is None and m["avisos"] == []
    assert m["acuse_criticos"]["minutos_promedio"] is None
