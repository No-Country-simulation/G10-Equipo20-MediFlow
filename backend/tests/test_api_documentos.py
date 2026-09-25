"""Paso 5: endpoint de ingesta. La API rechaza con código explícito (RN-A1) y nunca
pierde un documento que llegó (RN-P1)."""

CUERPO = {
    "documento_id": "DOC-CLIN-2026-8942",
    "canal_origen": "Guardia_Emergencias",
    "tipo_contenido": "texto",
    "contenido_texto": "TC de tórax: tromboembolismo pulmonar agudo.",
}


def test_post_documentos_devuelve_202_validado(client):
    r = client.post("/documentos", json=CUERPO)
    assert r.status_code == 202
    cuerpo = r.json()
    assert cuerpo["documento_id"] == "DOC-CLIN-2026-8942"
    assert cuerpo["estado"] == "VALIDADO"
    assert cuerpo["version"] == 1
    assert cuerpo["status_backup"] == "ok"
    assert cuerpo["ruta_storage"] == "co/recibidos/DOC-CLIN-2026-8942.txt"


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


def test_duplicado_exacto_devuelve_200_sin_reprocesar_RN_O1(client):
    client.post("/documentos", json=CUERPO)
    r = client.post("/documentos", json=CUERPO)
    assert r.status_code == 200
    assert r.json()["duplicado"] is True
    assert r.json()["version"] == 1


def test_get_documento_muestra_estado_y_transiciones_RN_I3(client):
    client.post("/documentos", json=CUERPO)
    r = client.get("/documentos/DOC-CLIN-2026-8942")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "VALIDADO"
    assert [t["a_estado"] for t in cuerpo["transiciones"]] == ["RECIBIDO", "VALIDADO"]
    assert all(t["actor"] == "sistema" for t in cuerpo["transiciones"])


def test_get_documento_inexistente_es_404(client):
    assert client.get("/documentos/NO-EXISTE").status_code == 404
