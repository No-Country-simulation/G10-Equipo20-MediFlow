"""Paso 5: endpoint de ingesta. La API rechaza con código explícito (RN-A1) y nunca
pierde un documento que llegó (RN-P1)."""

CUERPO = {
    "documento_id": "DOC-CLIN-2026-8942",
    "canal_origen": "Guardia_Emergencias",
    "tipo_contenido": "texto",
    "contenido_texto": "Paciente: Carlos Eduardo Mendes, 52 años. Fecha: 03/04/2026. TC de tórax: tromboembolismo pulmonar agudo. Dr. Andrés Rojas, RM 45678.",
}


def test_post_documentos_procesa_y_devuelve_200(client, llm_falso):
    from tests.test_llm import propuesta_caso_1

    llm_falso.respuestas.append(propuesta_caso_1())
    r = client.post("/documentos", json=CUERPO)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["documento_id"] == "DOC-CLIN-2026-8942"
    assert cuerpo["estado"] == "ENRUTADO"
    assert cuerpo["version"] == 1
    assert cuerpo["status_backup"] == "ok"
    assert cuerpo["ruta_storage"] == "co/procesados/criticos/DOC-CLIN-2026-8942.json"
    assert cuerpo["resultado"]["documento_id"] == "DOC-CLIN-2026-8942"


def test_sin_LLM_configurado_el_documento_va_a_revision_humana_RN_P2(client, llm_falso):
    from app.services.llm import ErrorTransitorioLLM

    llm_falso.respuestas.extend([ErrorTransitorioLLM("sin clave")] * 3)
    r = client.post("/documentos", json=CUERPO)
    assert r.status_code == 200
    assert r.json()["estado"] == "EN_REVISION_HUMANA"


def test_sin_canal_origen_es_422_RN_A9(client):
    datos = {k: v for k, v in CUERPO.items() if k != "canal_origen"}
    r = client.post("/documentos", json=datos)
    assert r.status_code == 422


def test_formato_no_soportado_es_422_RN_A1(client):
    r = client.post("/documentos", json={**CUERPO, "tipo_contenido": "docx"})
    assert r.status_code == 422


def test_rechazo_por_tamano_es_400_con_codigo_RN_O5(client):
    r = client.post("/documentos", json={**CUERPO, "contenido_texto": "x" * 20_000_000})
    assert r.status_code == 400
    assert r.json()["codigo_error"] == "tamano_excedido"
    assert r.json()["estado"] == "RECHAZADO"


def test_duplicado_exacto_devuelve_200_sin_reprocesar_RN_O1(client, llm_falso):
    from tests.test_llm import propuesta_caso_1

    llm_falso.respuestas.append(propuesta_caso_1())
    client.post("/documentos", json=CUERPO)
    r = client.post("/documentos", json=CUERPO)
    assert r.status_code == 200
    assert r.json()["duplicado"] is True
    assert r.json()["version"] == 1
    assert len(llm_falso.llamadas) == 1


def test_get_documento_muestra_estado_y_transiciones_RN_I3(client, llm_falso):
    from tests.test_llm import propuesta_caso_1

    llm_falso.respuestas.append(propuesta_caso_1())
    client.post("/documentos", json=CUERPO)
    r = client.get("/documentos/DOC-CLIN-2026-8942")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "ENRUTADO"
    assert [t["a_estado"] for t in cuerpo["transiciones"]] == ["RECIBIDO", "VALIDADO", "CLASIFICADO", "EXTRAIDO", "EVALUADO", "ENRUTADO"]
    assert all(t["actor"] == "sistema" for t in cuerpo["transiciones"])


def test_get_documento_inexistente_es_404(client):
    assert client.get("/documentos/NO-EXISTE").status_code == 404


def test_el_mapa_de_reidentificacion_nunca_sale_por_la_api_RN_M1(client, llm_falso):
    from app.services.llm import ErrorTransitorioLLM

    llm_falso.respuestas.extend([ErrorTransitorioLLM("sin clave")] * 3)
    cuerpo = {**CUERPO, "contenido_texto": "Paciente: Carlos Eduardo Mendes, 52 años. CC 1.020.304.050."}
    client.post("/documentos", json=cuerpo)
    r = client.get("/documentos/DOC-CLIN-2026-8942")
    assert "mapa_reidentificacion" not in r.json()
    assert "texto_seudonimizado" not in r.json()
