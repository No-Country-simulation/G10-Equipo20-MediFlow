"""Transcripción humana de un documento en fallo técnico (RN-P2, RN-J3, RN-J4, RN-J8).

Sin lectura del LLM no hay propuesta que corregir. La persona que revisa transcribe los datos
desde el original y las reglas determinísticas se aplican igual que sobre una propuesta del LLM:
la prioridad solo puede subir (RN-D8), los hallazgos críticos del texto se mantienen (RN-P4)
y cada dato transcrito queda registrado como corrección (RN-J8).
"""
from app.services.llm import ErrorTransitorioLLM
from tests.test_aceptacion import TEXTO_RECETA, med, receta

AUDITOR = {"usuario": "aud.ana", "rol": "auditor_clinico"}
TEXTO_TEP = ("TC de tórax. Fecha: 03/04/2026. Paciente: Carlos Eduardo Mendes, 52 años. Hallazgo: tromboembolismo pulmonar agudo "
             "bilateral. Dr. Andrés Rojas, RM 45678.")


def enviar_con_fallo(client, llm_falso, documento_id, texto, canal="Consulta_Ambulatoria"):
    llm_falso.respuestas.extend([ErrorTransitorioLLM("sin clave")] * 3)
    r = client.post("/documentos", json={"documento_id": documento_id, "canal_origen": canal, "tipo_contenido": "texto", "contenido_texto": texto})
    assert r.status_code == 200, r.text
    detalle = client.get(f"/documentos/{documento_id}").json()
    assert detalle["estado"] == "EN_REVISION_HUMANA"
    assert detalle["resultado"]["evaluacion"]["motivo_auditoria"] == "fallo_tecnico"
    return detalle


def transcripcion_receta() -> dict:
    """Lo que una persona transcribe de la fórmula de losartán: la misma forma que propondría el LLM."""
    completa = receta([med("losartan", "50 mg")], documento={"tipo": "CC", "valor": "41234567"})
    # una persona transcribe valores reales, no los tokens de la seudonimización
    completa["extraccion"]["paciente"]["nombre"] = "Ana María Pérez"
    completa["extraccion"]["profesional"]["nombre"] = "Carolina Duque"
    completa["extraccion"]["fecha_documento"] = "03/04/2026"
    return {"clasificacion": {"tipo": "Receta Médica", "nivel_prioridad_propuesto": "Rutina", "dominio": "Cardiología", "especialidad": "Cardiología"},
            "extraccion": completa["extraccion"], "condiciones": {"recetario_oficial": None}}


def transcribir(client, documento_id, transcripcion, motivo="transcrito desde el original"):
    return client.post(f"/revision/{documento_id}/resolver", json={**AUDITOR, "accion": "transcribir", "motivo": motivo, "transcripcion": transcripcion})


def test_una_receta_en_fallo_tecnico_se_transcribe_y_se_enruta_como_si_la_hubiera_leido_el_llm(client, llm_falso):
    enviar_con_fallo(client, llm_falso, "FT-REC", TEXTO_RECETA)
    r = transcribir(client, "FT-REC", transcripcion_receta())
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == "ENRUTADO"
    assert cuerpo["resultado"]["enrutamiento"]["destino_principal"] == "Farmacia_Hospitalaria"
    detalle = client.get("/documentos/FT-REC").json()
    assert detalle["resultado"]["clasificacion"]["tipo"] == "Receta Médica"
    decisiones = [d["regla"] + ":" + d["decision"] for d in detalle["resultado"]["historial_decisiones"]]
    assert any(d.startswith("RN-J3:transcrito") for d in decisiones)
    # RN-J8: cada dato transcrito queda como par extraído-corregido, con el extraído vacío
    campos = {c["campo"]: c for c in detalle["correcciones"]}
    assert campos["clasificacion.tipo"]["extraido"] is None and campos["clasificacion.tipo"]["corregido"] == "Receta Médica"
    assert campos["extraccion.medicamentos"]["usuario"] == "aud.ana"
    assert [t["a_estado"] for t in detalle["transiciones"]][-3:] == ["RESUELTO", "EVALUADO", "ENRUTADO"]


def test_la_transcripcion_no_baja_un_critico_detectado_en_el_texto_RN_D8(client, llm_falso):
    enviar_con_fallo(client, llm_falso, "FT-TEP", TEXTO_TEP, canal="Guardia_Emergencias")
    assert client.get("/documentos/FT-TEP").json()["nivel_prioridad"] == "Crítico"  # RN-P4: detección por texto
    alertas_antes = len(client.get("/alertas").json())
    transcripcion = {
        "clasificacion": {"tipo": "Informe de Imágenes", "nivel_prioridad_propuesto": "Rutina", "dominio": "Neumología", "especialidad": "Radiología"},
        "extraccion": {"paciente": {"edad": 52, "documento": {"tipo": None, "valor": None}}, "profesional": {"nombre": "Andrés Rojas", "registro_profesional": "RM 45678"},
                       "fecha_documento": "03/04/2026", "diagnosticos": [{"texto": "Tromboembolismo pulmonar agudo", "cie10_sugerido": "I26.9"}]},
    }
    r = transcribir(client, "FT-TEP", transcripcion)
    assert r.status_code == 200, r.text
    assert r.json()["resultado"]["clasificacion"]["nivel_prioridad"] == "Crítico"
    assert len(client.get("/alertas").json()) == alertas_antes  # RN-Q1: la alerta no se duplica


def test_transcribir_exige_tipo_de_documento_y_datos_con_la_forma_de_la_propuesta(client, llm_falso):
    enviar_con_fallo(client, llm_falso, "FT-1", TEXTO_RECETA)
    sin_tipo = transcribir(client, "FT-1", {"extraccion": {"fecha_documento": "03/04/2026"}})
    assert sin_tipo.status_code == 422 and "tipo" in sin_tipo.json()["detail"]
    inventado = transcribir(client, "FT-1", {"clasificacion": {"tipo": "Receta Médica"}, "campo_inventado": 1})
    assert inventado.status_code == 422
    assert client.get("/documentos/FT-1").json()["estado"] == "EN_REVISION_HUMANA"


def test_solo_se_transcribe_lo_que_no_tiene_lectura_del_llm(client, llm_falso):
    llm_falso.respuestas.append(receta([med("losartan", "50 mg")], **{"confianzas.medicamento_dosis": 0.90}))
    client.post("/documentos", json={"documento_id": "CON-LLM", "canal_origen": "Consulta_Ambulatoria", "tipo_contenido": "texto", "contenido_texto": TEXTO_RECETA})
    assert client.get("/documentos/CON-LLM").json()["estado"] == "EN_REVISION_HUMANA"
    r = transcribir(client, "CON-LLM", transcripcion_receta())
    assert r.status_code == 409 and "corregir" in r.json()["detail"]


def test_transcribir_respeta_la_separacion_de_funciones_RN_K2(client, llm_falso):
    enviar_con_fallo(client, llm_falso, "FT-2", TEXTO_RECETA)
    client.post("/administracion/usuarios", json={"usuario": "gestor.ana", "nombre": "Ana", "rol": "gestor", "tipo": "persona", "actor": "admin"})
    r = client.post("/revision/FT-2/resolver", json={"usuario": "gestor.ana", "rol": "gestor", "accion": "transcribir", "motivo": "x", "transcripcion": transcripcion_receta()})
    assert r.status_code == 403
