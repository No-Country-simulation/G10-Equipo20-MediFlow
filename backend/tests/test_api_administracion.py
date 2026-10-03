"""Fase D: administración de usuarios y accesos (RN-K1 a RN-K5), ficha del pack y puesta en marcha (RN-S3).

Toda acción la firma la cuenta de la sesión, sujeta a su rol, a su tipo y a su estado (RN-K2, RN-K4, RN-K5).
"""
from tests.test_aceptacion import med, propuesta, receta, sample, TEXTO_RECETA
from tests.test_api_farmacia_autorizaciones import enviar

from tests.conftest import CLAVE_PRUEBAS


def crear(admin, usuario, rol, nombre="Persona", tipo="persona"):
    return admin.post("/administracion/usuarios", json={"usuario": usuario, "nombre": nombre, "rol": rol, "tipo": tipo})


def enviar_tep(client, llm_falso, documento_id):
    # contenido distinto por documento: un mismo contenido con otro ID no vuelve a alertar (RN-O3)
    enviar(client, llm_falso, documento_id, sample("caso01_tc_torax_tep.txt") + f"\nRef. interna {documento_id}",
           propuesta(**{"extraccion.paciente.documento": {"tipo": None, "valor": None}}), canal="Guardia_Emergencias")


# --- Usuarios ---------------------------------------------------------------------------------


def test_alta_listado_y_validaciones_de_usuarios(client, admin):
    r = crear(admin, "jefe.rojas", "jefe_urgencias", nombre="Andrés Rojas")
    assert r.status_code == 201, r.text
    assert r.json()["usuario"] == "jefe.rojas" and r.json()["activo"] is True and r.json()["tipo"] == "persona"
    assert crear(admin, "jefe.rojas", "jefe_urgencias").status_code == 409
    assert crear(admin, "x.y", "rol_inexistente").status_code == 422
    assert crear(admin, "bot", "gestor", tipo="robot").status_code == 422
    lista = admin.get("/administracion/usuarios").json()
    assert [u["usuario"] for u in lista if u["creado_por"] == "admin.root"] == ["jefe.rojas"]  # las demás son las sesiones de la suite
    assert "creado_en" in lista[0]


def test_RN_K4_usuario_desactivado_pierde_acceso_y_su_historial_permanece(client, llm_falso, jefe, admin):
    enviar_tep(client, llm_falso, "TEP-1")
    enviar_tep(client, llm_falso, "TEP-2")
    assert jefe.post("/alertas/TEP-1/acuse").status_code == 200
    r = admin.post("/administracion/usuarios/jefe.rojas/desactivar")
    assert r.status_code == 200 and r.json()["activo"] is False and r.json()["desactivado_en"]
    # RN-K4: efecto inmediato, también sobre la sesión que tenía abierta
    bloqueado = jefe.post("/alertas/TEP-2/acuse")
    assert bloqueado.status_code == 401
    assert jefe.post("/auth/ingresar", json={"usuario": "jefe.rojas", "clave": CLAVE_PRUEBAS}).status_code == 401
    assert client.get("/documentos/TEP-2").json()["alerta"]["estado_acuse"] == "pendiente"
    # sus acciones históricas permanecen
    assert client.get("/documentos/TEP-1").json()["alerta"]["acusado_por"] == "jefe.rojas"
    assert admin.post("/administracion/usuarios/jefe.rojas/activar").json()["activo"] is True
    assert jefe.post("/auth/ingresar", json={"usuario": "jefe.rojas", "clave": CLAVE_PRUEBAS}).status_code == 200
    assert jefe.post("/alertas/TEP-2/acuse").status_code == 200
    assert admin.post("/administracion/usuarios/nadie/desactivar").status_code == 404


def test_RN_K5_una_cuenta_de_servicio_no_ejecuta_acciones_clinicas(client, llm_falso, como):
    bot = como("bot.farmacia", "quimico_farmaceutico", tipo="servicio")
    enviar(bot, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))  # integrar documentos sí es trabajo de servicio
    r = bot.post("/farmacia/REC-1/verificar")
    assert r.status_code == 403 and "RN-K5" in r.json()["detail"]
    assert client.get("/documentos/REC-1").json()["estado"] == "ENRUTADO"


def test_RN_K2_quien_configura_no_revisa_y_cada_rol_solo_su_accion_RN_K1(client, llm_falso, gestor, quimico, anonimo):
    enviar(client, llm_falso, "REC-DUD", TEXTO_RECETA, receta([med("losartan", "50 mg")], **{"confianzas.medicamento_dosis": 0.90}))
    enviar_tep(client, llm_falso, "TEP-1")
    cuerpo = {"accion": "aprobar", "motivo": "ok"}
    r = gestor.post("/revision/REC-DUD/resolver", json=cuerpo)
    assert r.status_code == 403 and "RN-K2" in r.json()["detail"]
    r = quimico.post("/alertas/TEP-1/acuse")
    assert r.status_code == 403 and "RN-K2" in r.json()["detail"]
    assert client.post("/revision/REC-DUD/resolver", json=cuerpo).status_code == 200
    # sin sesión nadie firma nada (RN-K5)
    assert anonimo.post("/alertas/TEP-1/acuse").status_code == 401


def test_RN_K3_todo_acceso_a_un_documento_queda_registrado(client, llm_falso, admin):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    assert client.get("/documentos/REC-1").status_code == 200
    assert client.get("/documentos/REC-1/original").status_code == 200
    accesos = admin.get("/administracion/accesos", params={"documento_id": "REC-1"}).json()
    assert [(a["usuario"], a["accion"]) for a in accesos] == [("aud.ana", "original"), ("aud.ana", "detalle")]
    assert all(a["fecha_hora"] for a in accesos)
    assert len(admin.get("/administracion/accesos").json()) == 2
    assert "Pérez" not in admin.get("/administracion/accesos").text  # RN-M4


# --- Pack y puesta en marcha ------------------------------------------------------------------------


def test_ficha_del_pack_sin_datos_clinicos(client, admin):
    r = admin.get("/administracion/pack")
    assert r.status_code == 200
    pack = r.json()
    assert pack["pais"] == "CO" and pack["version_pack"]
    assert pack["terminologia"]["diagnosticos"] in {"CIE-10", "CIE-11", "dual"}
    assert pack["retencion"]["anios"] == 15 and pack["retencion"]["purga_automatica"] is False
    assert pack["listas"]["hallazgos_criticos"] >= 1 and pack["listas"]["alto_riesgo"] >= 1
    assert isinstance(pack["por_confirmar"], list)


def test_RN_S3_puesta_en_marcha_lista_los_requisitos_minimos(client, llm_falso, admin, como):
    antes = admin.get("/administracion/puesta_en_marcha").json()
    por_clave = {r["clave"]: r for r in antes["requisitos"]}
    assert por_clave["pais"]["cumplido"] is True
    assert por_clave["auditor_clinico"]["cumplido"] is True  # la sesión de `client`
    assert por_clave["jefe_urgencias"]["cumplido"] is False
    assert por_clave["alerta_prueba_con_acuse"]["cumplido"] is False
    assert por_clave["claves_definitivas"]["cumplido"] is True
    assert antes["listo"] is False

    jefe_turno = como("jefe.turno", "jefe_urgencias")
    enviar_tep(client, llm_falso, "TEP-PRUEBA")
    jefe_turno.post("/alertas/TEP-PRUEBA/acuse")
    crear(admin, "nuevo.aud", "auditor_clinico")  # con clave inicial: el administrador la define y su dueño la cambia al entrar
    admin.post("/administracion/usuarios/nuevo.aud/clave", json={"clave": "Clave.inicial.2026"})
    despues = {r["clave"]: r for r in admin.get("/administracion/puesta_en_marcha").json()["requisitos"]}
    assert despues["auditor_clinico"]["cumplido"] and despues["jefe_urgencias"]["cumplido"] and despues["alerta_prueba_con_acuse"]["cumplido"]
    assert despues["claves_definitivas"]["cumplido"] is False and "nuevo.aud" in despues["claves_definitivas"]["detalle"]
    assert {"base_legal", "contrato_transmision", "destinos_activos"} <= set(despues)
