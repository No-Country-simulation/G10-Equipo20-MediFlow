"""Fase D: administración de usuarios y accesos (RN-K1 a RN-K5), ficha del pack y puesta en marcha (RN-S3).

Sin autenticación en el MVP: un usuario no registrado sigue pudiendo firmar (como hasta ahora);
un usuario registrado queda sujeto a su rol, a su tipo y a su estado.
"""
from tests.test_aceptacion import med, propuesta, receta, sample, TEXTO_RECETA
from tests.test_api_farmacia_autorizaciones import enviar

ADMIN = {"actor": "admin.root"}


def crear(client, usuario, rol, nombre="Persona", tipo="persona"):
    return client.post("/administracion/usuarios", json={"usuario": usuario, "nombre": nombre, "rol": rol, "tipo": tipo, **ADMIN})


def enviar_tep(client, llm_falso, documento_id):
    # contenido distinto por documento: un mismo contenido con otro ID no vuelve a alertar (RN-O3)
    enviar(client, llm_falso, documento_id, sample("caso01_tc_torax_tep.txt") + f"\nRef. interna {documento_id}",
           propuesta(**{"extraccion.paciente.documento": {"tipo": None, "valor": None}}), canal="Guardia_Emergencias")


# --- Usuarios ---------------------------------------------------------------------------------


def test_alta_listado_y_validaciones_de_usuarios(client):
    r = crear(client, "jefe.rojas", "jefe_urgencias", nombre="Andrés Rojas")
    assert r.status_code == 201, r.text
    assert r.json()["usuario"] == "jefe.rojas" and r.json()["activo"] is True and r.json()["tipo"] == "persona"
    assert crear(client, "jefe.rojas", "jefe_urgencias").status_code == 409
    assert crear(client, "x.y", "rol_inexistente").status_code == 422
    assert crear(client, "bot", "gestor", tipo="robot").status_code == 422
    lista = client.get("/administracion/usuarios").json()
    assert [u["usuario"] for u in lista] == ["jefe.rojas"]
    assert "creado_en" in lista[0]


def test_RN_K4_usuario_desactivado_pierde_acceso_y_su_historial_permanece(client, llm_falso):
    crear(client, "jefe.rojas", "jefe_urgencias")
    enviar_tep(client, llm_falso, "TEP-1")
    enviar_tep(client, llm_falso, "TEP-2")
    assert client.post("/alertas/TEP-1/acuse", json={"usuario": "jefe.rojas"}).status_code == 200
    r = client.post("/administracion/usuarios/jefe.rojas/desactivar", json=ADMIN)
    assert r.status_code == 200 and r.json()["activo"] is False and r.json()["desactivado_en"]
    bloqueado = client.post("/alertas/TEP-2/acuse", json={"usuario": "jefe.rojas"})
    assert bloqueado.status_code == 403 and "RN-K4" in bloqueado.json()["detail"]
    assert client.get("/documentos/TEP-2").json()["alerta"]["estado_acuse"] == "pendiente"
    # sus acciones históricas permanecen
    assert client.get("/documentos/TEP-1").json()["alerta"]["acusado_por"] == "jefe.rojas"
    assert client.post("/administracion/usuarios/jefe.rojas/activar", json=ADMIN).json()["activo"] is True
    assert client.post("/alertas/TEP-2/acuse", json={"usuario": "jefe.rojas"}).status_code == 200
    assert client.post("/administracion/usuarios/nadie/desactivar", json=ADMIN).status_code == 404


def test_RN_K5_una_cuenta_de_servicio_no_ejecuta_acciones_clinicas(client, llm_falso):
    crear(client, "bot.integracion", "quimico_farmaceutico", tipo="servicio")
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    r = client.post("/farmacia/REC-1/verificar", json={"usuario": "bot.integracion"})
    assert r.status_code == 403 and "RN-K5" in r.json()["detail"]
    assert client.get("/documentos/REC-1").json()["estado"] == "ENRUTADO"


def test_RN_K2_quien_configura_no_revisa_y_cada_rol_solo_su_accion_RN_K1(client, llm_falso):
    crear(client, "gestor.ana", "gestor")
    crear(client, "qf.maria", "quimico_farmaceutico")
    crear(client, "aud.ana", "auditor_clinico")
    enviar(client, llm_falso, "REC-DUD", TEXTO_RECETA, receta([med("losartan", "50 mg")], **{"confianzas.medicamento_dosis": 0.90}))
    enviar_tep(client, llm_falso, "TEP-1")
    cuerpo = {"accion": "aprobar", "motivo": "ok"}
    r = client.post("/revision/REC-DUD/resolver", json={**cuerpo, "usuario": "gestor.ana", "rol": "gestor"})
    assert r.status_code == 403 and "RN-K2" in r.json()["detail"]
    # el rol declarado en la petición debe coincidir con el registrado
    r = client.post("/revision/REC-DUD/resolver", json={**cuerpo, "usuario": "aud.ana", "rol": "jefe_urgencias"})
    assert r.status_code == 403 and "RN-K1" in r.json()["detail"]
    r = client.post("/alertas/TEP-1/acuse", json={"usuario": "qf.maria"})
    assert r.status_code == 403
    assert client.post("/revision/REC-DUD/resolver", json={**cuerpo, "usuario": "aud.ana", "rol": "auditor_clinico"}).status_code == 200
    # un usuario no registrado sigue firmando (MVP sin autenticación)
    assert client.post("/alertas/TEP-1/acuse", json={"usuario": "jefe.sin.registro"}).status_code == 200


def test_RN_K3_todo_acceso_a_un_documento_queda_registrado(client, llm_falso):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    assert client.get("/documentos/REC-1", headers={"X-Usuario": "aud.ana"}).status_code == 200
    assert client.get("/documentos/REC-1/original", headers={"X-Usuario": "aud.ana"}).status_code == 200
    client.get("/documentos/REC-1")  # sin usuario: no hay a quién atribuirlo
    accesos = client.get("/administracion/accesos", params={"documento_id": "REC-1"}).json()
    assert [(a["usuario"], a["accion"]) for a in accesos] == [("aud.ana", "original"), ("aud.ana", "detalle")]
    assert all(a["fecha_hora"] for a in accesos)
    assert len(client.get("/administracion/accesos").json()) == 2
    assert "Pérez" not in client.get("/administracion/accesos").text  # RN-M4


# --- Pack y puesta en marcha ------------------------------------------------------------------------


def test_ficha_del_pack_sin_datos_clinicos(client):
    r = client.get("/administracion/pack")
    assert r.status_code == 200
    pack = r.json()
    assert pack["pais"] == "CO" and pack["version_pack"]
    assert pack["terminologia"]["diagnosticos"] in {"CIE-10", "CIE-11", "dual"}
    assert pack["retencion"]["anios"] == 15 and pack["retencion"]["purga_automatica"] is False
    assert pack["listas"]["hallazgos_criticos"] >= 1 and pack["listas"]["alto_riesgo"] >= 1
    assert isinstance(pack["por_confirmar"], list)


def test_RN_S3_puesta_en_marcha_lista_los_requisitos_minimos(client, llm_falso):
    antes = client.get("/administracion/puesta_en_marcha").json()
    por_clave = {r["clave"]: r for r in antes["requisitos"]}
    assert por_clave["pais"]["cumplido"] is True
    assert por_clave["auditor_clinico"]["cumplido"] is False
    assert por_clave["jefe_urgencias"]["cumplido"] is False
    assert por_clave["alerta_prueba_con_acuse"]["cumplido"] is False
    assert antes["listo"] is False

    crear(client, "aud.ana", "auditor_clinico")
    crear(client, "jefe.rojas", "jefe_urgencias")
    enviar_tep(client, llm_falso, "TEP-PRUEBA")
    client.post("/alertas/TEP-PRUEBA/acuse", json={"usuario": "jefe.rojas"})
    despues = {r["clave"]: r for r in client.get("/administracion/puesta_en_marcha").json()["requisitos"]}
    assert despues["auditor_clinico"]["cumplido"] and despues["jefe_urgencias"]["cumplido"] and despues["alerta_prueba_con_acuse"]["cumplido"]
    assert {"base_legal", "contrato_transmision", "destinos_activos"} <= set(despues)
