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


# --- Archivos reales, listado, original y vista previa (mejora de la rama bryan-segovia) ------


from pathlib import Path as _Path

MUESTRAS = _Path(__file__).resolve().parents[2] / "samples" / "archivos"


def test_post_documentos_archivo_acepta_multipart(client, llm_falso):
    from tests.test_llm import propuesta_caso_1

    llm_falso.respuestas.append(propuesta_caso_1())
    r = client.post("/documentos/archivo",
                    data={"documento_id": "DOC-UP-1", "canal_origen": "Consulta_Ambulatoria", "cobertura_paciente": "contributivo"},
                    files={"archivo": ("cardio_digital.pdf", (MUESTRAS / "cardio_digital.pdf").read_bytes(), "application/pdf")})
    assert r.status_code == 200, r.text
    assert r.json()["documento_id"] == "DOC-UP-1"
    assert r.json()["formato"] == "pdf"
    assert "ECOCARDIOGRAMA" in llm_falso.llamadas[-1].texto_usuario  # texto embebido, ruta de texto


def test_post_documentos_archivo_escaneado_manda_la_imagen_al_LLM_RN_M2(client, llm_falso):
    from tests.test_llm import propuesta_caso_1

    llm_falso.respuestas.append(propuesta_caso_1())
    r = client.post("/documentos/archivo", data={"documento_id": "DOC-UP-2", "canal_origen": "Externo"},
                    files={"archivo": ("cardio_scan.pdf", (MUESTRAS / "cardio_scan.pdf").read_bytes(), "application/pdf")})
    assert r.status_code == 200, r.text
    assert len(llm_falso.llamadas[-1].imagenes) == 1
    assert llm_falso.llamadas[-1].imagenes[0][1] == "image/png"


def test_post_documentos_archivo_rechazado_es_400_con_codigo(client):
    r = client.post("/documentos/archivo", data={"documento_id": "DOC-UP-3", "canal_origen": "Externo"},
                    files={"archivo": ("informe.docx", b"PK\x03\x04 no", "application/octet-stream")})
    assert r.status_code == 400
    assert r.json()["codigo_error"] == "formato_no_soportado"


def test_get_documentos_lista_paginada_con_filtros(client, llm_falso):
    from app.services.llm import ErrorTransitorioLLM
    from tests.test_llm import propuesta_caso_1

    llm_falso.respuestas.append(propuesta_caso_1())
    client.post("/documentos", json={**CUERPO, "documento_id": "DOC-L-1"})
    llm_falso.respuestas.extend([ErrorTransitorioLLM("x")] * 3)
    client.post("/documentos", json={**CUERPO, "documento_id": "DOC-L-2", "contenido_texto": "Control de rutina. Fecha: 03/04/2026."})
    todos = client.get("/documentos").json()
    assert todos["total"] == 2 and [d["documento_id"] for d in todos["items"]] == ["DOC-L-2", "DOC-L-1"]
    revision = client.get("/documentos", params={"estado": "EN_REVISION_HUMANA"}).json()
    assert [d["documento_id"] for d in revision["items"]] == ["DOC-L-2"]
    buscados = client.get("/documentos", params={"q": "L-1", "limit": 1}).json()
    assert buscados["total"] == 1 and buscados["items"][0]["nivel_prioridad"] == "Crítico"
    assert "resultado" not in buscados["items"][0]


def test_get_original_y_vista_previa(client, llm_falso):
    from tests.test_llm import propuesta_caso_1

    llm_falso.respuestas.append(propuesta_caso_1())
    client.post("/documentos/archivo", data={"documento_id": "DOC-UP-4", "canal_origen": "Externo"},
                files={"archivo": ("cardio_mixed.pdf", (MUESTRAS / "cardio_mixed.pdf").read_bytes(), "application/pdf")})
    original = client.get("/documentos/DOC-UP-4/original")
    assert original.status_code == 200
    assert original.headers["content-type"] == "application/pdf"
    assert original.content.startswith(b"%PDF")
    previa = client.get("/documentos/DOC-UP-4/vista_previa", params={"pagina": 2})
    assert previa.status_code == 200
    assert previa.headers["content-type"] == "image/png"
    assert previa.headers["x-paginas"] == "2"
    assert client.get("/documentos/DOC-UP-4/vista_previa", params={"pagina": 3}).status_code == 404


def test_original_de_documento_de_texto_se_sirve_como_texto(client, llm_falso):
    from tests.test_llm import propuesta_caso_1

    llm_falso.respuestas.append(propuesta_caso_1())
    client.post("/documentos", json=CUERPO)
    r = client.get("/documentos/DOC-CLIN-2026-8942/original")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert client.get("/documentos/DOC-CLIN-2026-8942/vista_previa").status_code == 415
