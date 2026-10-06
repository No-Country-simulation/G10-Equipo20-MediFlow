"""RN-R2: cada corrección humana alimenta un conjunto de referencia seudonimizado.

El conjunto guarda lo que vio el LLM (con tokens), lo que propuso, lo que la persona corrigió y la prioridad antes
y después. Nunca lleva nombres ni documentos reales (RN-M1, RN-M4). Lo ve el gestor, con las métricas.
"""
from app.services.referencia import Seudonimo
from tests.test_api_revision import enviar, propuesta_para_revision, propuesta_rutina_dudosa, TEXTO, TEXTO_RUTINA

MAPA = {"[PACIENTE_1]": "Carlos Eduardo Mendes", "[PROFESIONAL_1]": "Andrés Rojas"}


# --- regla pura: el mapa al revés y lo que no estaba en el mapa -----------------------------------


def test_el_seudonimo_devuelve_los_tokens_y_enmascara_lo_identificante_nuevo():
    s = Seudonimo(MAPA)
    assert s.texto("TC de Carlos Eduardo Mendes, firma Andrés Rojas") == "TC de [PACIENTE_1], firma [PROFESIONAL_1]"
    assert s.valor("Carlos Eduardo Mendes", "extraccion.paciente.nombre") == "[PACIENTE_1]"
    assert s.valor("Carlos E. Mendes", "extraccion.paciente.nombre") == "[PACIENTE_C1]"  # lo escribió la persona: token nuevo
    assert s.valor("Carlos E. Mendes", "extraccion.paciente.nome") == "[PACIENTE_C1]"  # el mismo valor, el mismo token
    assert s.valor("80123456", "extraccion.paciente.documento.valor") == "[ID_C2]"
    assert s.valor("I26.0", "extraccion.diagnosticos[0].cie10_sugerido") == "I26.0"  # un código no identifica a nadie
    assert s.valor({"paciente": {"nombre": "Carlos Eduardo Mendes", "edad": 52}}, "extraccion") == {"paciente": {"nombre": "[PACIENTE_1]", "edad": 52}}
    assert Seudonimo(None).valor("Ana", "extraccion.profesional.nombre") == "[PROFESIONAL_C1]"


# --- por la API ----------------------------------------------------------------------------------------


def test_RN_R2_una_correccion_entra_al_conjunto_seudonimizada_con_su_contexto(client, llm_falso, gestor):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    assert gestor.get("/metricas/referencia").json()["resumen"]["casos"] == 0
    r = client.post("/revision/DOC-CRIT/resolver", json={"accion": "corregir", "motivo": "código confirmado",
                                                         "correcciones": {"extraccion.diagnosticos[0].cie10_sugerido": "I26.0", "confianzas.diagnostico_codigo": 0.99}})
    assert r.status_code == 200, r.text

    cuerpo = gestor.get("/metricas/referencia").json()
    assert cuerpo["resumen"]["casos"] == 2 and cuerpo["resumen"]["documentos"] == 1 and cuerpo["resumen"]["por_origen"] == {"correccion": 2}
    assert {c["campo"] for c in cuerpo["resumen"]["por_campo"]} == {"extraccion.diagnosticos.*.cie10_sugerido", "confianzas.diagnostico_codigo"}
    caso = next(c for c in cuerpo["casos"] if c["campo"] == "extraccion.diagnosticos[0].cie10_sugerido")
    assert caso["corregido"] == "I26.0" and caso["usuario"] == "aud.ana" and caso["origen"] == "correccion"
    assert caso["documento_id"] == "DOC-CRIT" and caso["tipo_documento"] == "Informe de Imágenes" and caso["canal_origen"] == "Guardia_Emergencias"
    assert caso["nivel_propuesto"] == "Crítico" and caso["nivel_antes"] == "Crítico" and caso["nivel_resultante"] == "Crítico"
    assert caso["hallazgos"] == ["TEP_AGUDO"] and caso["modelo_llm"] == "falso" and caso["version_reglas"] and caso["version_pack"]
    assert "Mendes" not in gestor.get("/metricas/referencia").text  # RN-M4

    exportado = gestor.get("/metricas/referencia/exportar")
    assert exportado.status_code == 200 and "attachment" in exportado.headers["content-disposition"]
    completo = exportado.json()
    assert len(completo) == 2 and "[PACIENTE_1]" in completo[0]["texto_seudonimizado"] and "Mendes" not in exportado.text
    assert completo[0]["propuesta"]["extraccion"]["paciente"]["nombre"] == "[PACIENTE_1]"  # la propuesta vuelve a sus tokens
    assert completo[0]["propuesta"]["extraccion"]["profesional"]["nombre"] == "[PROFESIONAL_1]"


def test_un_nombre_escrito_por_la_persona_no_entra_en_claro(client, llm_falso, gestor):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    client.post("/revision/DOC-CRIT/resolver", json={"accion": "corregir", "motivo": "nombre según el original",
                                                     "correcciones": {"extraccion.paciente.nombre": "Carlos Eduardo Méndez"}})
    casos = gestor.get("/metricas/referencia").json()["casos"]
    assert casos[0]["extraido"] == "[PACIENTE_1]" and casos[0]["corregido"] == "[PACIENTE_C1]"
    assert "Méndez" not in gestor.get("/metricas/referencia/exportar").text


def test_cada_correccion_entra_una_sola_vez_aunque_el_documento_se_vuelva_a_persistir(client, llm_falso, gestor):
    enviar(client, llm_falso, "DOC-RUT-1", propuesta_rutina_dudosa(), texto=TEXTO_RUTINA)
    r = client.post("/revision/DOC-RUT-1/resolver", json={"accion": "corregir", "motivo": "sigue dudoso", "correcciones": {"extraccion.fecha_documento": "03/04/2026"}})
    assert r.json()["estado"] == "EN_REVISION_HUMANA"  # la corrección no resolvió la duda: vuelve a revisión
    assert client.post("/revision/DOC-RUT-1/resolver", json={"accion": "rechazar", "motivo": "documento de otra institución"}).status_code == 200
    assert gestor.get("/metricas/referencia").json()["resumen"]["casos"] == 1


def test_subir_a_critico_queda_contado_para_la_compuerta_de_calidad_RN_R3(client, llm_falso, gestor):
    enviar(client, llm_falso, "DOC-RUT-1", propuesta_rutina_dudosa(), texto=TEXTO_RUTINA)
    r = client.post("/revision/DOC-RUT-1/resolver", json={"accion": "corregir", "motivo": "el informe describe un TEP",
                                                          "correcciones": {"nivel_prioridad": "Crítico", "clasificacion.score_confianza": 0.95}})
    assert r.status_code == 200, r.text
    resumen = gestor.get("/metricas/referencia").json()["resumen"]
    assert resumen["subidos_a_critico"] == ["DOC-RUT-1"]
    caso = next(c for c in gestor.get("/metricas/referencia").json()["casos"] if c["campo"] == "nivel_prioridad")
    assert caso["extraido"] == "Rutina" and caso["corregido"] == "Crítico" and caso["nivel_antes"] == "Rutina" and caso["nivel_resultante"] == "Crítico"


def test_una_transcripcion_tambien_alimenta_el_conjunto(client, llm_falso, gestor):
    from app.services.llm import ErrorTransitorioLLM

    llm_falso.respuestas.extend([ErrorTransitorioLLM("caído")] * 3)
    client.post("/documentos", json={"documento_id": "DOC-FT", "canal_origen": "Externo", "tipo_contenido": "texto", "contenido_texto": TEXTO})
    assert client.get("/documentos/DOC-FT").json()["estado"] == "EN_REVISION_HUMANA"
    r = client.post("/revision/DOC-FT/resolver", json={"accion": "transcribir", "motivo": "transcrito", "transcripcion": {
        "clasificacion": {"tipo": "Informe de Imágenes", "nivel_prioridad_propuesto": "Rutina"},
        "extraccion": {"paciente": {"nombre": "Carlos Eduardo Mendes", "edad": 52}, "fecha_documento": "03/04/2026"}}})
    assert r.status_code == 200, r.text
    cuerpo = gestor.get("/metricas/referencia").json()
    assert cuerpo["resumen"]["por_origen"] == {"transcripcion": cuerpo["resumen"]["casos"]} and cuerpo["resumen"]["casos"] >= 3
    nombre = next(c for c in cuerpo["casos"] if c["campo"] == "extraccion.paciente.nombre")
    assert nombre["corregido"] == "[PACIENTE_1]" and nombre["extraido"] is None  # el nombre sí estaba en el mapa del texto
    assert "Mendes" not in gestor.get("/metricas/referencia/exportar").text


def test_el_conjunto_lo_ve_el_gestor_y_no_los_roles_clinicos_RN_K2(client, jefe, gestor):
    assert gestor.get("/metricas/referencia").status_code == 200
    assert client.get("/metricas/referencia").status_code == 403
    assert jefe.get("/metricas/referencia/exportar").status_code == 403
