"""RN-R3: un cambio de modelo, prompt o reglas no sale a producción si empeora los falsos negativos críticos.

La compuerta corre las reglas sobre el conjunto de referencia (RN-R2): con la configuración vigente y con la
propuesta. Si aparece un falso negativo crítico nuevo, la versión no se activa. Para modelo y prompt, el script
vuelve a pedir la propuesta al LLM sobre el texto seudonimizado y compara contra una línea base.

Los documentos de estas pruebas son críticos solo por el hallazgo del pack (sin signos vitales ni palabras
críticas en el texto): así un pack sin hallazgos críticos representa un cambio de reglas que sí empeora.
"""
import pytest

from app.packs.loader import cargar_pack, cargar_umbrales
from app.services.compuerta import DocumentoReferencia, comparar, evaluar_conjunto
from app.services.configuracion import ErrorConfiguracion, ServicioConfiguracion
from app.services.llm import ClienteFalso
from scripts.compuerta_calidad import ejecutar
from tests.test_api_configuracion import proponer
from tests.test_api_revision import enviar, propuesta_rutina_dudosa

TEXTO_CONTROL = "Paciente: Carlos Eduardo Mendes, 52 años. Fecha: 03/04/2026. Informe de control sin novedad. Dr. Andrés Rojas, RM 45678."
TEXTO_TOKENS = "Paciente: [PACIENTE_1], 52 años. Fecha: 03/04/2026. Informe de control sin novedad. Dr. [PROFESIONAL_1], RM 45678."


def propuesta_tep_por_hallazgo() -> dict:
    """Signos vitales normales y texto neutro: el Crítico sale solo del hallazgo TEP_AGUDO y del código I26.0 del pack."""
    p = propuesta_rutina_dudosa()
    p["extraccion"]["hallazgos_criticos_detectados"] = ["TEP_AGUDO"]
    p["extraccion"]["diagnosticos"] = [{"texto": "Tromboembolismo", "cie10_sugerido": "I26.0", "cie11_sugerido": None}]
    return p


def documento(nivel_esperado="Crítico", propuesta=None, documento_id="DOC-REF") -> DocumentoReferencia:
    return DocumentoReferencia(documento_id=documento_id, version=1, canal_origen="Guardia_Emergencias", pais="CO", texto=TEXTO_TOKENS,
                               propuesta=propuesta_tep_por_hallazgo() if propuesta is None else propuesta, nivel_esperado=nivel_esperado)


def pack_sin_hallazgos():
    """Un cambio de reglas que sí empeora: sin hallazgos críticos el pack no reconoce el TEP."""
    return cargar_pack("CO").model_copy(update={"hallazgos_criticos": []})


def documento_corregido(client, llm_falso, documento_id="DOC-CRIT"):
    """Un documento en revisión por baja confianza, corregido por una persona: queda en el conjunto como Crítico."""
    enviar(client, llm_falso, documento_id, propuesta_tep_por_hallazgo(), texto=TEXTO_CONTROL)
    r = client.post(f"/revision/{documento_id}/resolver", json={"accion": "corregir", "motivo": "código confirmado",
                                                               "correcciones": {"clasificacion.score_confianza": 0.95}})
    assert r.status_code == 200, r.text


# --- reglas puras -------------------------------------------------------------------------------------


def test_un_critico_que_las_reglas_no_llevan_a_critico_es_falso_negativo():
    pack, umbrales = cargar_pack("CO"), cargar_umbrales()
    r = evaluar_conjunto([documento()], pack, umbrales)
    assert r.documentos == 1 and r.criticos_esperados == 1 and r.falsos_negativos == []
    r = evaluar_conjunto([documento()], pack_sin_hallazgos(), umbrales)
    assert r.falsos_negativos == [{"documento_id": "DOC-REF", "version": 1, "esperado": "Crítico", "obtenido": "Rutina"}]
    # lo que una persona dejó en Rutina no cuenta; sin propuesta no se evalúa
    r = evaluar_conjunto([documento("Rutina"), documento(propuesta={}, documento_id="VACIO")], pack_sin_hallazgos(), umbrales)
    assert r.criticos_esperados == 0 and r.sin_propuesta == 1 and r.falsos_negativos == []


def test_empeora_solo_si_aparece_un_falso_negativo_nuevo():
    pack, umbrales = cargar_pack("CO"), cargar_umbrales()
    docs = [documento(), documento(documento_id="OTRO")]
    bien = evaluar_conjunto(docs, pack, umbrales)
    mal = evaluar_conjunto(docs, pack_sin_hallazgos(), umbrales)
    assert comparar(bien, mal)["empeora"] is True and comparar(bien, mal)["nuevos_falsos_negativos"] == ["DOC-REF@1", "OTRO@1"]
    assert comparar(mal, mal)["empeora"] is False  # los que ya existían no bloquean
    assert comparar(mal, bien)["empeora"] is False and comparar(mal, bien)["propuesto"]["falsos_negativos"] == 0


# --- en la configuración (RN-L6 y RN-L4 con la compuerta) ----------------------------------------------


def test_la_simulacion_y_la_propuesta_llevan_la_compuerta_y_una_version_que_no_empeora_se_activa(client, llm_falso, gestor):
    enviar(client, llm_falso, "DOC-RUT-1", propuesta_rutina_dudosa(), texto=TEXTO_CONTROL)
    client.post("/revision/DOC-RUT-1/resolver", json={"accion": "corregir", "motivo": "el informe describe un TEP",
                                                      "correcciones": {"nivel_prioridad": "Crítico", "clasificacion.score_confianza": 0.95}})
    sim = gestor.post("/configuracion/simular", json={"cambios": {"umbrales": {"confianza.medicamento_dosis": 0.98}}}).json()
    compuerta = sim["compuerta"]
    assert compuerta["documentos"] == 1 and compuerta["criticos_esperados"] == 1
    # el LLM dijo Rutina y una persona lo subió: hoy es falso negativo, y el cambio de umbral no lo toca
    assert compuerta["actual"]["falsos_negativos"] == 1 and compuerta["propuesto"]["falsos_negativos"] == 1
    assert compuerta["nuevos_falsos_negativos"] == [] and compuerta["empeora"] is False
    assert "Mendes" not in str(sim)  # RN-M4

    p = proponer(gestor, {"umbrales": {"confianza.medicamento_dosis": 0.98}}).json()
    assert p["simulacion"]["compuerta"]["empeora"] is False
    aprobada = gestor.post(f"/configuracion/propuestas/{p['id']}/aprobar").json()
    assert aprobada["estado"] == "vigente" and aprobada["simulacion"]["compuerta"]["documentos"] == 1


def test_RN_R3_una_version_que_empeora_no_se_activa(client, llm_falso, gestor, session, monkeypatch):
    documento_corregido(client, llm_falso)
    p = proponer(gestor, {"umbrales": {"confianza.medicamento_dosis": 0.98}}).json()
    assert p["simulacion"]["compuerta"]["actual"]["falsos_negativos"] == 0
    # Ningún cambio configurable puede quitar un hallazgo crítico (RN-L3), así que el empeoramiento se simula
    # haciendo que la configuración propuesta pierda los hallazgos: la vigente sigue intacta.
    monkeypatch.setattr(ServicioConfiguracion, "validar", lambda self, cambios, pais: (self.umbrales(), pack_sin_hallazgos()))
    r = gestor.post(f"/configuracion/propuestas/{p['id']}/aprobar")
    assert r.status_code == 409, r.text
    assert "RN-R3" in r.json()["detail"] and "DOC-CRIT@1" in r.json()["detail"], r.text
    cfg = gestor.get("/configuracion").json()
    assert cfg["vigente"]["numero"] == 0 and cfg["propuestas"][0]["aprobaciones"] == []  # sigue la base: ni se activó ni se contó la aprobación
    assert cfg["propuestas"][0]["simulacion"]["compuerta"]["empeora"] is True  # y la propuesta muestra por qué
    with pytest.raises(ErrorConfiguracion):
        ServicioConfiguracion(session).aprobar(p["id"], "gestor.ana", pais="CO")


# --- el script: línea base y modelo o prompt nuevos ------------------------------------------------------


def test_el_script_compara_con_la_linea_base_y_sale_con_1_si_empeora(client, llm_falso, gestor, session, monkeypatch):
    documento_corregido(client, llm_falso)
    informe, codigo = ejecutar(session)
    assert codigo == 0 and informe["modo"] == "reglas" and informe["documentos"] == 1 and informe["falsos_negativos"] == 0
    assert informe["version_prompt"] == "triaje_v1"

    monkeypatch.setattr(ServicioConfiguracion, "pack", lambda self, pais: pack_sin_hallazgos())
    informe, codigo = ejecutar(session, linea_base={"detalle": []})
    assert codigo == 1 and informe["empeora"] is True and informe["nuevos_falsos_negativos"] == ["DOC-CRIT@1"]
    informe, codigo = ejecutar(session, linea_base={"detalle": [{"documento_id": "DOC-CRIT", "version": 1, "esperado": "Crítico", "obtenido": "Rutina"}]})
    assert codigo == 0 and informe["empeora"] is False  # ya estaba en la línea base: no es nuevo


def test_con_llm_el_script_vuelve_a_pedir_la_propuesta_sobre_el_texto_seudonimizado(client, llm_falso, gestor, session):
    documento_corregido(client, llm_falso)
    modelo_nuevo = ClienteFalso(respuestas=[propuesta_rutina_dudosa()], tokens=(1, 1), modelo="modelo-nuevo")  # ya no ve el TEP
    informe, codigo = ejecutar(session, linea_base={"detalle": []}, llm=modelo_nuevo)
    assert codigo == 1 and informe["modo"] == "llm" and informe["modelo"] == "modelo-nuevo"
    assert informe["nuevos_falsos_negativos"] == ["DOC-CRIT@1"]
    llamada = modelo_nuevo.llamadas[0]
    assert "[PACIENTE_1]" in llamada.texto_usuario and "Mendes" not in llamada.texto_usuario  # solo texto seudonimizado (RN-M1)

    mismo_modelo = ClienteFalso(respuestas=[propuesta_tep_por_hallazgo()], tokens=(1, 1), modelo="modelo-nuevo")
    informe, codigo = ejecutar(session, linea_base={"detalle": []}, llm=mismo_modelo)
    assert codigo == 0 and informe["falsos_negativos"] == 0
