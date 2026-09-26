"""Fase C: Farmacia con doble verificación (RN-E6, RN-J6, RN-CO9), Autorizaciones (RN-E5, RN-E9, RN-CO13)
y resumen de contadores para el inicio de cada rol."""
from tests.test_aceptacion import med, orden, receta, TEXTO_ORDEN, TEXTO_RECETA
from tests.test_llm import propuesta_caso_1


def enviar(client, llm_falso, documento_id, texto, propuesta_llm, canal="Consulta_Ambulatoria", cobertura=None):
    llm_falso.respuestas.append(propuesta_llm)
    cuerpo = {"documento_id": documento_id, "canal_origen": canal, "tipo_contenido": "texto", "contenido_texto": texto}
    if cobertura:
        cuerpo["cobertura_paciente"] = cobertura
    r = client.post("/documentos", json=cuerpo)
    assert r.status_code == 200, r.text
    return r.json()


# --- Farmacia ------------------------------------------------------------------------


def test_farmacia_lista_recetas_enrutadas_con_sus_marcas(client, llm_falso):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    enviar(client, llm_falso, "REC-2", TEXTO_RECETA.replace("Losartán", "Apixabán"), receta([med("apixaban", "5 mg")]))
    enviar(client, llm_falso, "IMG-1", "Fecha: 03/04/2026. Paciente: Ana Pérez, 58 años. TC normal. Dr. Rojas, RM 45678.",
           {**propuesta_caso_1(), "clasificacion": {**propuesta_caso_1()["clasificacion"], "nivel_prioridad_propuesto": "Rutina"},
            "extraccion": {**propuesta_caso_1()["extraccion"], "hallazgos_criticos_detectados": [], "diagnosticos": [{"texto": "Normal", "cie10_sugerido": "Z00.0", "cie11_sugerido": None}],
                           "signos_vitales": {"FR": 16, "SpO2": 97, "FC": 70, "PAS": 120, "Temp": None, "nivel_conciencia": "alerta"}}})
    cola = client.get("/farmacia").json()
    assert [r["documento_id"] for r in cola] == ["REC-2", "REC-1"]  # alto riesgo primero
    apixaban = cola[0]
    assert apixaban["alto_riesgo"] is True and apixaban["verificaciones_requeridas"] == 2
    assert apixaban["medicamentos"][0]["dci"] == "apixaban"
    assert cola[1]["verificaciones_requeridas"] == 1
    assert "Mendes" not in client.get("/farmacia").text and "Pérez" not in client.get("/farmacia").text


def test_receta_simple_se_verifica_con_una_firma_y_queda_entregada(client, llm_falso):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    r = client.post("/farmacia/REC-1/verificar", json={"usuario": "qf.maria"})
    assert r.status_code == 200, r.text
    assert r.json()["verificaciones"] == [{"orden": 1, "usuario": "qf.maria"}] or r.json()["verificaciones"][0]["usuario"] == "qf.maria"
    assert r.json()["completa"] is True
    assert client.get("/documentos/REC-1").json()["estado"] == "ENTREGADO"
    assert client.get("/farmacia").json() == []


def test_alto_riesgo_exige_dos_personas_distintas_RN_J6(client, llm_falso):
    enviar(client, llm_falso, "REC-2", TEXTO_RECETA, receta([med("apixaban", "5 mg")]))
    primera = client.post("/farmacia/REC-2/verificar", json={"usuario": "qf.maria"})
    assert primera.status_code == 200 and primera.json()["completa"] is False
    assert client.get("/documentos/REC-2").json()["estado"] == "ENRUTADO"
    repetida = client.post("/farmacia/REC-2/verificar", json={"usuario": "qf.maria"})
    assert repetida.status_code == 409
    assert "RN-J6" in repetida.json()["detail"]
    segunda = client.post("/farmacia/REC-2/verificar", json={"usuario": "qf.pedro"})
    assert segunda.status_code == 200 and segunda.json()["completa"] is True
    assert [v["usuario"] for v in segunda.json()["verificaciones"]] == ["qf.maria", "qf.pedro"]
    assert client.get("/documentos/REC-2").json()["estado"] == "ENTREGADO"


def test_verificar_exige_usuario_y_solo_recetas_enrutadas(client, llm_falso):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    assert client.post("/farmacia/REC-1/verificar", json={"usuario": " "}).status_code == 422
    enviar(client, llm_falso, "ORD-1", TEXTO_ORDEN, orden(), cobertura="contributivo")
    assert client.post("/farmacia/ORD-1/verificar", json={"usuario": "qf.maria"}).status_code == 409
    assert client.post("/farmacia/NO-EXISTE/verificar", json={"usuario": "qf.maria"}).status_code == 404


# --- Autorizaciones ------------------------------------------------------------------------


def test_autorizaciones_separa_por_autorizar_de_avisos_de_urgencias_RN_CO13(client, llm_falso):
    enviar(client, llm_falso, "ORD-AMB", TEXTO_ORDEN, orden(), cobertura="contributivo")
    enviar(client, llm_falso, "ORD-URG", TEXTO_ORDEN, orden(), canal="Guardia_Emergencias")
    enviar(client, llm_falso, "ORD-INC", TEXTO_ORDEN, orden(justificacion=None), cobertura="contributivo")
    bandeja = client.get("/autorizaciones").json()
    assert [o["documento_id"] for o in bandeja["por_autorizar"]] == ["ORD-INC", "ORD-AMB"] or {o["documento_id"] for o in bandeja["por_autorizar"]} == {"ORD-AMB", "ORD-INC"}
    assert [o["documento_id"] for o in bandeja["avisos_urgencias"]] == ["ORD-URG"]
    amb = next(o for o in bandeja["por_autorizar"] if o["documento_id"] == "ORD-AMB")
    assert amb["cobertura"] == "contributivo" and amb["motivo_destino"] == "solicitud_autorizacion_eps"
    assert amb["cups"] == ["372100"] and amb["documentacion_incompleta"] is False
    inc = next(o for o in bandeja["por_autorizar"] if o["documento_id"] == "ORD-INC")
    assert inc["documentacion_incompleta"] is True and inc["motivo_destino"] == "documentacion_incompleta"
    assert "Castro" not in client.get("/autorizaciones").text


def test_aprobar_autorizacion_confirma_la_entrega_a_auditoria(client, llm_falso):
    enviar(client, llm_falso, "ORD-AMB", TEXTO_ORDEN, orden(), cobertura="contributivo")
    r = client.post("/autorizaciones/ORD-AMB/resolver", json={"accion": "aprobar", "usuario": "aut.luis", "motivo": "cumple justificación"})
    assert r.status_code == 200, r.text
    assert r.json()["autorizacion"]["estado"] == "aprobada"
    detalle = client.get("/documentos/ORD-AMB").json()
    assert detalle["estado"] == "ENTREGADO"
    assert any(h["regla"] == "RN-E9" and "aut.luis" in h["evidencia"] for h in detalle["resultado"]["historial_decisiones"])
    assert client.get("/autorizaciones").json()["por_autorizar"] == []


def test_devolver_exige_motivo_y_registra_la_devolucion_RN_E5(client, llm_falso):
    enviar(client, llm_falso, "ORD-INC", TEXTO_ORDEN, orden(justificacion=None), cobertura="contributivo")
    assert client.post("/autorizaciones/ORD-INC/resolver", json={"accion": "devolver", "usuario": "aut.luis", "motivo": ""}).status_code == 422
    r = client.post("/autorizaciones/ORD-INC/resolver", json={"accion": "devolver", "usuario": "aut.luis", "motivo": "falta justificación clínica"})
    assert r.status_code == 200
    assert r.json()["autorizacion"] == {"estado": "devuelta", "usuario": "aut.luis", "motivo": "falta justificación clínica", "fecha_hora": r.json()["autorizacion"]["fecha_hora"]}
    detalle = client.get("/documentos/ORD-INC").json()
    assert detalle["autorizacion"]["estado"] == "devuelta"
    assert any(h["regla"] == "RN-E5" and h["decision"] == "devuelta_al_solicitante" for h in detalle["resultado"]["historial_decisiones"])


def test_solo_ordenes_enrutadas_a_auditoria_se_resuelven(client, llm_falso):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    assert client.post("/autorizaciones/REC-1/resolver", json={"accion": "aprobar", "usuario": "aut.luis", "motivo": "x"}).status_code == 409
    assert client.post("/autorizaciones/NO/resolver", json={"accion": "aprobar", "usuario": "aut.luis", "motivo": "x"}).status_code == 404


# --- Resumen para el inicio del rol --------------------------------------------------------------


def test_resumen_cuenta_por_estado_prioridad_y_alertas(client, llm_falso):
    from app.services.llm import ErrorTransitorioLLM

    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    enviar(client, llm_falso, "CRIT-1", "Paciente: Carlos Mendes, 52 años. Fecha: 03/04/2026. TC: tromboembolismo pulmonar agudo. Dr. Rojas, RM 45678.", propuesta_caso_1(), canal="Guardia_Emergencias")
    llm_falso.respuestas.extend([ErrorTransitorioLLM("x")] * 3)
    client.post("/documentos", json={"documento_id": "REV-1", "canal_origen": "Externo", "tipo_contenido": "texto", "contenido_texto": "Control. Fecha: 03/04/2026."})
    resumen = client.get("/resumen").json()
    assert resumen["total"] == 3
    assert resumen["por_estado"]["ENRUTADO"] == 2 and resumen["por_estado"]["EN_REVISION_HUMANA"] == 1
    assert resumen["por_prioridad"]["Crítico"] == 1 and resumen["por_prioridad"]["Rutina"] == 2
    assert resumen["alertas_sin_acuse"] == 1
    assert resumen["en_revision"] == 1
    assert resumen["recetas_por_verificar"] == 1
    assert resumen["ordenes_por_autorizar"] == 0
    assert resumen["entregados_hoy"] == 0
