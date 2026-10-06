"""Paso 10: API de revisión humana (RN-J), acuse (RN-Q5, RN-J7) y entrega (RN-I).

El cliente de la API usa un LLM falso inyectado por conftest.
"""
import copy
from datetime import timedelta

from app.packs.loader import cargar_umbrales
from app.repositories.documentos import RepositorioDocumentos
from app.services.escalamiento import escalar_una_vuelta
from app.services.revision_humana import ServicioRevision, _utc
from app.services.usuarios import ServicioUsuarios
from tests.conftest import crear_cuenta
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


def test_la_cola_muestra_el_hallazgo_critico_para_no_abrir_cada_caso(client, llm_falso):
    """La señal clínica va en la cola: el revisor ve qué es cada caso sin abrirlo. Sin datos del paciente (RN-M4)."""
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    enviar(client, llm_falso, "DOC-RUT-1", propuesta_rutina_dudosa(), texto=TEXTO_RUTINA)
    por_id = {d["documento_id"]: d for d in client.get("/revision").json()}
    assert por_id["DOC-CRIT"]["hallazgos"] == ["TEP_AGUDO"]
    assert por_id["DOC-RUT-1"]["hallazgos"] == []
    assert "Mendes" not in client.get("/revision").text


# --- Acciones del revisor (RN-J3) ---------------------------------------------------------------


def test_aprobar_manda_el_documento_a_su_plan_tras_revision_RN_J3(client, llm_falso):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    r = client.post("/revision/DOC-CRIT/resolver", json={"accion": "aprobar", "motivo": "hallazgo confirmado"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "ENRUTADO"
    assert cuerpo["resultado"]["enrutamiento"]["destino_principal"] == "Cola_Emergencia_Medica"
    assert cuerpo["resultado"]["evaluacion"]["requiere_auditoria_humana"] is False
    estados = [t["a_estado"] for t in client.get("/documentos/DOC-CRIT").json()["transiciones"]]
    assert estados[-3:] == ["EN_REVISION_HUMANA", "RESUELTO", "ENRUTADO"]
    assert client.get("/documentos/DOC-CRIT").json()["transiciones"][-1]["actor"] == "aud.ana"  # RN-G4: la cuenta de la sesión


def test_corregir_reejecuta_las_reglas_sin_volver_al_LLM_RN_J4_RN_J8(client, llm_falso):
    enviar(client, llm_falso, "DOC-RUT", propuesta_rutina_dudosa(), texto=TEXTO_RUTINA)
    llamadas_antes = len(llm_falso.llamadas)
    r = client.post("/revision/DOC-RUT/resolver", json={
        "accion": "corregir", "motivo": "clasificación confirmada",
        "correcciones": {"clasificacion.score_confianza": 0.99},
    })
    assert r.status_code == 200
    assert r.json()["estado"] == "ENRUTADO"
    assert len(llm_falso.llamadas) == llamadas_antes
    correcciones = client.get("/documentos/DOC-RUT").json()["correcciones"]
    assert correcciones == [{"campo": "clasificacion.score_confianza", "extraido": 0.6, "corregido": 0.99, "usuario": "aud.ana"}]


def test_corregir_puede_volver_a_dejarlo_en_revision(client, llm_falso):
    enviar(client, llm_falso, "DOC-RUT", propuesta_rutina_dudosa(), texto=TEXTO_RUTINA)
    r = client.post("/revision/DOC-RUT/resolver", json={
        "accion": "corregir", "motivo": "sigo dudando",
        "correcciones": {"clasificacion.score_confianza": 0.7},
    })
    assert r.json()["estado"] == "EN_REVISION_HUMANA"


def test_rechazar_exige_motivo_RN_I5_RN_J3(client, llm_falso):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    r = client.post("/revision/DOC-CRIT/resolver", json={"accion": "rechazar", "motivo": ""})
    assert r.status_code == 422
    r = client.post("/revision/DOC-CRIT/resolver", json={"accion": "rechazar", "motivo": "documento de otra institución"})
    assert r.status_code == 200
    assert r.json()["estado"] == "RECHAZADO"


def test_solo_rol_clinico_baja_un_critico_y_con_justificacion_RN_J5(client, llm_falso, autorizador):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    cuerpo = {"accion": "corregir", "motivo": "x",
              "correcciones": {"nivel_prioridad": "Urgente", "extraccion.hallazgos_criticos_detectados": [], "extraccion.diagnosticos": []}}
    assert autorizador.post("/revision/DOC-CRIT/resolver", json=cuerpo).status_code == 403  # un rol administrativo no revisa (RN-K2)
    cuerpo["motivo"] = ""
    assert client.post("/revision/DOC-CRIT/resolver", json=cuerpo).status_code == 422  # el clínico sí, pero con justificación escrita


def test_subir_prioridad_es_libre_RN_J5(client, llm_falso):
    enviar(client, llm_falso, "DOC-RUT", propuesta_rutina_dudosa(), texto=TEXTO_RUTINA)
    r = client.post("/revision/DOC-RUT/resolver", json={
        "accion": "corregir", "motivo": "lo veo urgente",
        "correcciones": {"nivel_prioridad": "Urgente", "clasificacion.score_confianza": 0.95},
    })
    assert r.status_code == 200
    assert r.json()["resultado"]["clasificacion"]["nivel_prioridad"] == "Urgente"


def test_documento_que_no_esta_en_revision_no_se_puede_resolver_RN_I4(client, llm_falso):
    enviar(client, llm_falso, "DOC-OK")
    r = client.post("/revision/DOC-OK/resolver", json={"accion": "aprobar", "motivo": "x"})
    assert r.status_code == 409


# --- Acuse y entrega (RN-Q5, RN-J7, RN-I) ----------------------------------------------------------


def test_acuse_lo_da_un_usuario_identificado_RN_Q5(client, llm_falso, jefe, anonimo):
    enviar(client, llm_falso, "DOC-1")
    assert anonimo.post("/alertas/DOC-1/acuse").status_code == 401  # un "leído" anónimo no cuenta
    r = jefe.post("/alertas/DOC-1/acuse")
    assert r.status_code == 200
    assert r.json()["estado_acuse"] == "acusado"
    assert r.json()["acusado_por"] == "jefe.rojas"  # la cuenta de la sesión, no un nombre escrito


def test_critico_no_se_cierra_sin_acuse_RN_J7(client, llm_falso, jefe):
    enviar(client, llm_falso, "DOC-1")
    client.post("/documentos/DOC-1/entregar", json={"destino": "Cola_Emergencia_Medica"})
    r = client.post("/documentos/DOC-1/entregar", json={"destino": "Historia_Clinica_Electronica"})
    assert r.json()["estado"] == "ENRUTADO"
    assert r.json()["pendientes"] == ["acuse_alerta"]
    jefe.post("/alertas/DOC-1/acuse")
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


# --- Listado de alertas para el banner global (fase A del rediseño) -------------------------------


def test_get_alertas_lista_las_pendientes_primero_y_oculta_datos_del_paciente_RN_Q4(client, llm_falso, jefe):
    enviar(client, llm_falso, "DOC-A1")
    enviar(client, llm_falso, "DOC-A2", texto=TEXTO + " Segunda toma.")
    jefe.post("/alertas/DOC-A1/acuse")
    todas = client.get("/alertas").json()
    assert [a["documento_id"] for a in todas] == ["DOC-A2", "DOC-A1"]
    assert todas[0]["estado_acuse"] == "pendiente" and todas[1]["estado_acuse"] == "acusado"
    assert todas[0]["plazo_minutos"] == 15  # RN-F2
    assert "Mendes" not in client.get("/alertas").text
    pendientes = client.get("/alertas", params={"estado_acuse": "pendiente"}).json()
    assert [a["documento_id"] for a in pendientes] == ["DOC-A2"]
    assert {"nivel", "mensaje", "canal", "destinatario", "emitida_en", "acusado_por", "concepto"} <= set(pendientes[0])
    assert pendientes[0]["concepto"] == "TEP_AGUDO"


# --- Reasignar y escalar (RN-J3) y plazo vencido en cola (RN-J2) ---------------------------------


def resolver(cliente, documento_id="DOC-CRIT", **cuerpo):
    return cliente.post(f"/revision/{documento_id}/resolver", json=cuerpo)


def test_reasignar_deja_el_caso_en_revision_a_nombre_de_otro_revisor_RN_J3(client, llm_falso, jefe):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    r = resolver(client, accion="reasignar", asignar_a="jefe.rojas", motivo="requiere criterio del jefe")
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "EN_REVISION_HUMANA"  # no decide nada: el grafo sigue esperando
    ultima = r.json()["resultado"]["historial_decisiones"][-1]
    assert ultima["regla"] == "RN-J3" and ultima["decision"] == "reasignado a jefe.rojas"
    assert ultima["evidencia"] == "aud.ana (auditor_clinico): requiere criterio del jefe"
    item = client.get("/revision").json()[0]
    assert item["asignado_a"] == "jefe.rojas" and item["escalado_a_rol"] is None
    assert client.get("/documentos/DOC-CRIT").json()["asignado_a"] == "jefe.rojas"
    # quien lo tomó lo resuelve: la decisión sigue abierta en el hilo del grafo (RN-I4)
    assert resolver(jefe, accion="aprobar", motivo="hallazgo confirmado").status_code == 200
    assert client.get("/documentos/DOC-CRIT").json()["estado"] == "ENRUTADO"


def test_reasignar_solo_a_una_persona_activa_cuyo_rol_resuelva_la_revision_RN_K2_RN_K4_RN_K5(client, llm_falso, gestor, servicio, jefe, session):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    ServicioUsuarios(session).cambiar_estado("jefe.rojas", activo=False)
    for cuenta in ("", "nadie.existe", "gestor.ana", "bot.integracion", "jefe.rojas"):
        r = resolver(client, accion="reasignar", asignar_a=cuenta)
        assert r.status_code == 422, (cuenta, r.text)
    assert client.get("/revision").json()[0]["asignado_a"] is None
    assert resolver(client, accion="reasignar", asignar_a="aud.ana").status_code == 200  # tomar el caso uno mismo
    assert client.get("/revision").json()[0]["asignado_a"] == "aud.ana"


def test_escalar_exige_motivo_y_sube_el_caso_al_jefe_de_urgencias_una_sola_vez_RN_J3(client, llm_falso, jefe):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    resolver(client, accion="reasignar", asignar_a="aud.ana")
    assert resolver(client, accion="escalar").status_code == 422
    r = resolver(client, accion="escalar", motivo="hallazgo fuera de mi criterio")
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "EN_REVISION_HUMANA"
    ultima = r.json()["resultado"]["historial_decisiones"][-1]
    assert ultima["regla"] == "RN-J3" and ultima["decision"] == "escalado a jefe_urgencias"
    item = client.get("/revision").json()[0]
    assert item["escalado_a_rol"] == "jefe_urgencias" and item["asignado_a"] is None  # pasa al rol, no a una persona
    assert resolver(client, accion="escalar", motivo="otra vez").status_code == 409
    # por encima del jefe no hay otro rol; el jefe sí puede devolverlo a un auditor, y eso cierra el escalamiento
    assert resolver(jefe, accion="escalar", motivo="más arriba").status_code == 409
    assert resolver(jefe, accion="reasignar", asignar_a="aud.ana", motivo="lo ve ana").status_code == 200
    item = client.get("/revision").json()[0]
    assert item["asignado_a"] == "aud.ana" and item["escalado_a_rol"] is None


def test_reasignar_y_escalar_solo_sobre_un_caso_en_revision_RN_I4(client, llm_falso, jefe):
    enviar(client, llm_falso, "DOC-1")  # queda enrutado
    assert resolver(client, "DOC-1", accion="escalar", motivo="x").status_code == 409
    assert resolver(client, "DOC-1", accion="reasignar", asignar_a="jefe.rojas").status_code == 409


def test_los_revisores_son_las_personas_activas_que_resuelven_la_revision_RN_J3(client, jefe, gestor, servicio, session):
    crear_cuenta(session, "aud.baja", "auditor_clinico")
    ServicioUsuarios(session).cambiar_estado("aud.baja", activo=False)
    r = client.get("/revision/revisores")
    assert r.status_code == 200
    por_usuario = {u["usuario"]: u for u in r.json()}
    assert set(por_usuario) == {"aud.ana", "jefe.rojas"}
    assert por_usuario["jefe.rojas"] == {"usuario": "jefe.rojas", "nombre": "Jefe Rojas", "rol": "jefe_urgencias"}
    assert "clave" not in r.text


def test_vencido_el_plazo_en_cola_el_caso_escala_solo_al_siguiente_rol_RN_J2(client, llm_falso, session, notificador_falso):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    enviar(client, llm_falso, "DOC-RUT-1", propuesta_rutina_dudosa(), texto=TEXTO_RUTINA)
    resolver(client, accion="reasignar", asignar_a="aud.ana")
    repo = RepositorioDocumentos(session)
    servicio = ServicioRevision(repo)
    cola = cargar_umbrales().tiempos.cola_revision
    doc = repo.ultima_version("DOC-CRIT")
    entrada = _utc(doc.creado_en)

    assert servicio.escalar_vencidas(cola, ahora=entrada + timedelta(minutes=cola.critico_min - 1)) == []
    escalados = servicio.escalar_vencidas(cola, ahora=entrada + timedelta(minutes=cola.critico_min))
    assert [d.documento_id for d in escalados] == ["DOC-CRIT"]  # la Rutina tiene 24 h
    assert doc.escalado_a_rol == "jefe_urgencias" and doc.asignado_a is None
    ultima = doc.resultado_json["historial_decisiones"][-1]
    assert ultima["regla"] == "RN-J2" and ultima["decision"] == "escalado a jefe_urgencias" and "lo tenía aud.ana" in ultima["evidencia"]
    assert servicio.escalar_vencidas(cola, ahora=entrada + timedelta(hours=3)) == []  # no vuelve a escalar
    por_id = {d["documento_id"]: d for d in client.get("/revision").json()}
    assert por_id["DOC-CRIT"]["escalado_a_rol"] == "jefe_urgencias" and por_id["DOC-RUT-1"]["escalado_a_rol"] is None

    # la vuelta periódica hace lo mismo con la Rutina cuando vence su plazo
    assert "DOC-RUT-1" in escalar_una_vuelta(session, notificador_falso, ahora=entrada + timedelta(hours=cola.rutina_h_habiles, minutes=1))
    assert repo.ultima_version("DOC-RUT-1").escalado_a_rol == "jefe_urgencias"
