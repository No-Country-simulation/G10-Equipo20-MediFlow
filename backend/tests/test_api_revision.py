"""Paso 10: API de revisión humana (RN-J), acuse (RN-Q5, RN-J7) y entrega (RN-I).

El cliente de la API usa un LLM falso inyectado por conftest.
"""
import copy

from tests.test_llm import propuesta_caso_1

TEXTO = "Paciente: Carlos Eduardo Mendes, 52 años. Fecha: 03/04/2026. TC de tórax: tromboembolismo pulmonar agudo. FR 28, SpO2 88 %. Dr. Andrés Rojas, RM 45678."
TEXTO_RUTINA = "Paciente: Ana Pérez, 40 años. Fecha: 03/04/2026. Rx de tórax: bronquitis leve. Control. Dr. Andrés Rojas, RM 45678."


def enviar(client, llm_falso, documento_id="DOC-1", propuesta=None, texto=TEXTO, canal="Guardia_Emergencias"):
    llm_falso.respuestas.append(propuesta or propuesta_caso_1())
    return client.post("/documentos", json={"documento_id": documento_id, "canal_origen": canal, "tipo_contenido": "texto", "contenido_texto": texto})


def propuesta_para_revision(**cambios) -> dict:
    p = propuesta_caso_1()
    p["confianzas"]["diagnostico_codigo"] = 0.5  # RN-D9: crítico con baja confianza -> revisión
    for k, v in cambios.items():
        p[k] = v
    return p


def propuesta_rutina_dudosa() -> dict:
    p = propuesta_caso_1()
    p["clasificacion"]["nivel_prioridad_propuesto"] = "Rutina"
    p["extraccion"]["diagnosticos"] = [{"texto": "Bronquitis", "cie10_sugerido": "J40", "cie11_sugerido": None}]
    p["extraccion"]["hallazgos_criticos_detectados"] = []
    p["extraccion"]["signos_vitales"] = {"FR": 16, "SpO2": 97, "FC": 70, "PAS": 120, "Temp": None, "nivel_conciencia": "alerta"}
    p["clasificacion"]["score_confianza"] = 0.6  # RN-B4
    return p


# --- POST /documentos ahora devuelve el JSON del brief -------------------------------------------


def test_post_documentos_devuelve_el_resultado_completo(client, llm_falso):
    r = enviar(client, llm_falso)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "ENRUTADO"
    assert cuerpo["resultado"]["clasificacion"]["nivel_prioridad"] == "Crítico"
    assert cuerpo["resultado"]["notificacion_generada"]["estado_acuse"] == "pendiente"
    assert "mapa_reidentificacion" not in cuerpo


# --- Cola de revisión (RN-J1) -------------------------------------------------------------------


def test_cola_se_ordena_por_prioridad_y_luego_antiguedad_RN_J1(client, llm_falso):
    enviar(client, llm_falso, "DOC-RUT-1", propuesta_rutina_dudosa(), texto=TEXTO_RUTINA)
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    enviar(client, llm_falso, "DOC-RUT-2", propuesta_rutina_dudosa(), texto=TEXTO_RUTINA + " Segunda consulta.")
    cola = client.get("/revision").json()
    assert [d["documento_id"] for d in cola] == ["DOC-CRIT", "DOC-RUT-1", "DOC-RUT-2"]
    assert cola[0]["plazo_minutos"] == 15  # RN-J2


# --- Acciones del revisor (RN-J3) ---------------------------------------------------------------


def test_aprobar_manda_el_documento_a_su_plan_tras_revision_RN_J3(client, llm_falso):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    r = client.post("/revision/DOC-CRIT/resolver", json={"accion": "aprobar", "usuario": "ana", "rol": "auditor_clinico", "motivo": "hallazgo confirmado"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "ENRUTADO"
    assert cuerpo["resultado"]["enrutamiento"]["destino_principal"] == "Cola_Emergencia_Medica"
    assert cuerpo["resultado"]["evaluacion"]["requiere_auditoria_humana"] is False
    estados = [t["a_estado"] for t in client.get("/documentos/DOC-CRIT").json()["transiciones"]]
    assert estados[-3:] == ["EN_REVISION_HUMANA", "RESUELTO", "ENRUTADO"]
    assert client.get("/documentos/DOC-CRIT").json()["transiciones"][-1]["actor"] == "ana"  # RN-G4


def test_corregir_reejecuta_las_reglas_sin_volver_al_LLM_RN_J4_RN_J8(client, llm_falso):
    enviar(client, llm_falso, "DOC-RUT", propuesta_rutina_dudosa(), texto=TEXTO_RUTINA)
    llamadas_antes = len(llm_falso.llamadas)
    r = client.post("/revision/DOC-RUT/resolver", json={
        "accion": "corregir", "usuario": "ana", "rol": "auditor_clinico", "motivo": "clasificación confirmada",
        "correcciones": {"clasificacion.score_confianza": 0.99},
    })
    assert r.status_code == 200
    assert r.json()["estado"] == "ENRUTADO"
    assert len(llm_falso.llamadas) == llamadas_antes
    correcciones = client.get("/documentos/DOC-RUT").json()["correcciones"]
    assert correcciones == [{"campo": "clasificacion.score_confianza", "extraido": 0.6, "corregido": 0.99, "usuario": "ana"}]


def test_corregir_puede_volver_a_dejarlo_en_revision(client, llm_falso):
    enviar(client, llm_falso, "DOC-RUT", propuesta_rutina_dudosa(), texto=TEXTO_RUTINA)
    r = client.post("/revision/DOC-RUT/resolver", json={
        "accion": "corregir", "usuario": "ana", "rol": "auditor_clinico", "motivo": "sigo dudando",
        "correcciones": {"clasificacion.score_confianza": 0.7},
    })
    assert r.json()["estado"] == "EN_REVISION_HUMANA"


def test_rechazar_exige_motivo_RN_I5_RN_J3(client, llm_falso):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    r = client.post("/revision/DOC-CRIT/resolver", json={"accion": "rechazar", "usuario": "ana", "rol": "auditor_clinico", "motivo": ""})
    assert r.status_code == 422
    r = client.post("/revision/DOC-CRIT/resolver", json={"accion": "rechazar", "usuario": "ana", "rol": "auditor_clinico", "motivo": "documento de otra institución"})
    assert r.status_code == 200
    assert r.json()["estado"] == "RECHAZADO"


def test_solo_rol_clinico_baja_un_critico_y_con_justificacion_RN_J5(client, llm_falso):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    cuerpo = {"accion": "corregir", "usuario": "luis", "rol": "auditor_autorizaciones", "motivo": "x",
              "correcciones": {"nivel_prioridad": "Urgente", "extraccion.hallazgos_criticos_detectados": [], "extraccion.diagnosticos": []}}
    assert client.post("/revision/DOC-CRIT/resolver", json=cuerpo).status_code == 403
    cuerpo["rol"] = "auditor_clinico"
    cuerpo["motivo"] = ""
    assert client.post("/revision/DOC-CRIT/resolver", json=cuerpo).status_code == 422


def test_subir_prioridad_es_libre_RN_J5(client, llm_falso):
    enviar(client, llm_falso, "DOC-RUT", propuesta_rutina_dudosa(), texto=TEXTO_RUTINA)
    r = client.post("/revision/DOC-RUT/resolver", json={
        "accion": "corregir", "usuario": "luis", "rol": "auditor_autorizaciones", "motivo": "lo veo urgente",
        "correcciones": {"nivel_prioridad": "Urgente", "clasificacion.score_confianza": 0.95},
    })
    assert r.status_code == 200
    assert r.json()["resultado"]["clasificacion"]["nivel_prioridad"] == "Urgente"


def test_documento_que_no_esta_en_revision_no_se_puede_resolver_RN_I4(client, llm_falso):
    enviar(client, llm_falso, "DOC-OK")
    r = client.post("/revision/DOC-OK/resolver", json={"accion": "aprobar", "usuario": "ana", "rol": "auditor_clinico", "motivo": "x"})
    assert r.status_code == 409


# --- Acuse y entrega (RN-Q5, RN-J7, RN-I) ----------------------------------------------------------


def test_acuse_lo_da_un_usuario_identificado_RN_Q5(client, llm_falso):
    enviar(client, llm_falso, "DOC-1")
    assert client.post("/alertas/DOC-1/acuse", json={"usuario": ""}).status_code == 422
    r = client.post("/alertas/DOC-1/acuse", json={"usuario": "jefe.urgencias"})
    assert r.status_code == 200
    assert r.json()["estado_acuse"] == "acusado"
    assert r.json()["acusado_por"] == "jefe.urgencias"


def test_critico_no_se_cierra_sin_acuse_RN_J7(client, llm_falso):
    enviar(client, llm_falso, "DOC-1")
    client.post("/documentos/DOC-1/entregar", json={"destino": "Cola_Emergencia_Medica"})
    r = client.post("/documentos/DOC-1/entregar", json={"destino": "Historia_Clinica_Electronica"})
    assert r.json()["estado"] == "ENRUTADO"
    assert r.json()["pendientes"] == ["acuse_alerta"]
    client.post("/alertas/DOC-1/acuse", json={"usuario": "jefe.urgencias"})
    r = client.get("/documentos/DOC-1").json()
    assert r["estado"] == "ENTREGADO"


def test_entrega_retenida_a_HCE_no_bloquea_el_cierre_pero_queda_registrada_RN_A4(client, llm_falso):
    enviar(client, llm_falso, "DOC-1")  # sin identificador: HCE retenida
    cuerpo = client.post("/documentos/DOC-1/entregar", json={"destino": "Cola_Emergencia_Medica"}).json()
    assert cuerpo["retenidas"] == {"Historia_Clinica_Electronica": "identidad_ausente_conciliar"}
    assert cuerpo["pendientes"] == ["acuse_alerta"]


def test_entregar_a_un_destino_que_no_esta_en_el_plan_es_400(client, llm_falso):
    enviar(client, llm_falso, "DOC-1")
    assert client.post("/documentos/DOC-1/entregar", json={"destino": "Farmacia_Hospitalaria"}).status_code == 400
