"""Situaciones fuera de la revisión que podían dejar la instalación sin salida (RN-S3, RN-K4, RN-P2, RN-O2, RN-J7, RN-I).

Cuentas: el único administrador se desactiva o olvida su clave, una cuenta bloqueada por intentos. Alertas: la
alerta viva es de una versión anterior. Lectura: el LLM falló por un rato y hay que reintentar sin transcribir a
mano. Entregas: una confirmación repetida.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.sesiones import clave_coincide
from app.services.llm import ErrorTransitorioLLM
from app.services.usuarios import ServicioUsuarios
from scripts.crear_administrador import crear_administrador, restablecer_administrador
from tests.conftest import CLAVE_PRUEBAS
from tests.test_api_revision import enviar, propuesta_para_revision, TEXTO
from tests.test_api_transcripcion import enviar_con_fallo
from tests.test_llm import propuesta_caso_1


def resolver(client, documento_id, **cuerpo):
    return client.post(f"/revision/{documento_id}/resolver", json=cuerpo)


# --- cuentas -----------------------------------------------------------------------------------------------


def test_RN_S3_el_ultimo_administrador_activo_no_se_puede_desactivar(admin, session):
    r = admin.post("/administracion/usuarios/admin.root/desactivar")
    assert r.status_code == 409 and "administrador activo" in r.json()["detail"]
    assert ServicioUsuarios(session).buscar("admin.root").activo is True
    assert admin.post("/administracion/usuarios", json={"usuario": "admin.dos", "nombre": "Segundo", "rol": "administrador", "tipo": "persona"}).status_code == 201
    assert admin.post("/administracion/usuarios/admin.root/desactivar").status_code == 200  # ya hay otro


def test_RN_K4_definir_la_clave_destraba_una_cuenta_bloqueada_por_intentos(client, admin, session, anonimo):
    cuenta = ServicioUsuarios(session).buscar("aud.ana")
    cuenta.bloqueado_hasta = datetime.now(timezone.utc) + timedelta(minutes=30)
    cuenta.intentos_fallidos = 2
    session.commit()
    assert anonimo.post("/auth/ingresar", json={"usuario": "aud.ana", "clave": CLAVE_PRUEBAS}).status_code in (401, 423, 429)
    r = admin.post("/administracion/usuarios/aud.ana/clave", json={"clave": "Nueva.Clave.2026"})
    assert r.status_code == 200 and r.json()["bloqueado_hasta"] is None
    r = anonimo.post("/auth/ingresar", json={"usuario": "aud.ana", "clave": "Nueva.Clave.2026"})
    assert r.status_code == 200, r.text


def test_el_unico_administrador_que_olvido_su_clave_la_restablece_desde_el_servidor(session):
    assert crear_administrador(session, "admin.sede", "Clave.Inicial.2026") == "creada"
    cuenta = ServicioUsuarios(session).buscar("admin.sede")
    cuenta.activo = False
    cuenta.bloqueado_hasta = datetime.now(timezone.utc) + timedelta(minutes=30)
    session.commit()
    assert crear_administrador(session, "admin.sede", "Otra.Clave.2026") == "ya_existe"  # sin --restablecer no se toca
    assert restablecer_administrador(session, "admin.sede", "Otra.Clave.2026") == "restablecida"
    cuenta = ServicioUsuarios(session).buscar("admin.sede")
    assert clave_coincide("Otra.Clave.2026", cuenta.clave_hash) and cuenta.activo and cuenta.bloqueado_hasta is None and cuenta.debe_cambiar_clave
    with pytest.raises(ValueError, match="no existe"):
        restablecer_administrador(session, "nadie", "Otra.Clave.2026")
    with pytest.raises(ValueError, match="ADMIN_CLAVE_INICIAL"):
        restablecer_administrador(session, "admin.sede", "corta")


# --- la alerta viva es de una versión anterior (RN-O2, RN-J7, RN-F1) ----------------------------------------


def test_RN_J7_la_version_nueva_no_cierra_sin_el_acuse_de_la_alerta_de_la_version_anterior(client, llm_falso, jefe):
    enviar(client, llm_falso, "DOC-V", propuesta_para_revision())  # v1: crítico en revisión, alerta pendiente
    enviar(client, llm_falso, "DOC-V", propuesta_para_revision(), texto=TEXTO + " Informe ampliado.")  # v2: sin alerta nueva (RN-O2)
    assert resolver(client, "DOC-V", accion="aprobar", motivo="confirmado").json()["estado"] == "ENRUTADO"
    for destino in ("Cola_Emergencia_Medica", "Historia_Clinica_Electronica"):
        r = client.post("/documentos/DOC-V/entregar", json={"destino": destino})
    assert r.json()["pendientes"] == ["acuse_alerta"] and r.json()["estado"] == "ENRUTADO"
    assert jefe.post("/alertas/DOC-V/acuse").status_code == 200
    assert client.get("/documentos/DOC-V").json()["estado"] == "ENTREGADO"


def test_RN_F1_rechazar_la_version_nueva_cierra_la_alerta_de_la_anterior(client, llm_falso):
    enviar(client, llm_falso, "DOC-V", propuesta_para_revision())
    enviar(client, llm_falso, "DOC-V", propuesta_para_revision(), texto=TEXTO + " Informe ampliado.")
    assert client.get("/alertas", params={"estado_acuse": "pendiente"}).json()[0]["version"] == 1
    assert resolver(client, "DOC-V", accion="rechazar", motivo="documento de otra institución").status_code == 200
    assert client.get("/alertas", params={"estado_acuse": "pendiente"}).json() == []


# --- el LLM falló por un rato: reintentar sin transcribir (RN-P2) -----------------------------------------


def test_RN_P2_reintentar_la_lectura_cuando_el_llm_vuelve(client, llm_falso):
    enviar_con_fallo(client, llm_falso, "DOC-FT", TEXTO)
    llamadas = len(llm_falso.llamadas)
    llm_falso.respuestas.append(propuesta_caso_1())  # el servicio volvió
    r = resolver(client, "DOC-FT", accion="reintentar", motivo="OpenAI estuvo caído")
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ENRUTADO" and r.json()["resultado"]["clasificacion"]["tipo"] == "Informe de Imágenes"
    assert len(llm_falso.llamadas) == llamadas + 1
    detalle = client.get("/documentos/DOC-FT").json()
    estados = [t["a_estado"] for t in detalle["transiciones"]]
    assert estados[-6:] == ["EN_REVISION_HUMANA", "RESUELTO", "CLASIFICADO", "EXTRAIDO", "EVALUADO", "ENRUTADO"]
    assert any(d["regla"] == "RN-J3" and d["decision"] == "reintento" for d in detalle["resultado"]["historial_decisiones"])
    assert detalle["transiciones"][-1]["actor"] == "aud.ana"


def test_RN_P2_si_el_llm_vuelve_a_fallar_el_caso_regresa_a_revision_con_su_historial(client, llm_falso):
    enviar_con_fallo(client, llm_falso, "DOC-FT", TEXTO)
    llm_falso.respuestas.extend([ErrorTransitorioLLM("sigue caído")] * 3)
    r = resolver(client, "DOC-FT", accion="reintentar", motivo="probando otra vez")
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "EN_REVISION_HUMANA" and r.json()["resultado"]["evaluacion"]["motivo_auditoria"] == "fallo_tecnico"
    historial = r.json()["resultado"]["historial_decisiones"]
    assert any(d["regla"] == "RN-J3" and d["decision"] == "reintento" for d in historial)  # RN-G2: el intento queda
    assert client.get("/revision").json()[0]["documento_id"] == "DOC-FT"  # sigue en la cola, y se puede transcribir o reintentar
    llm_falso.respuestas.append(propuesta_caso_1())
    assert resolver(client, "DOC-FT", accion="reintentar", motivo="ahora sí").json()["estado"] == "ENRUTADO"


def test_reintentar_solo_aplica_a_un_fallo_tecnico(client, llm_falso):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())  # tiene lectura: lo que corresponde es corregir
    r = resolver(client, "DOC-CRIT", accion="reintentar", motivo="x")
    assert r.status_code == 409 and "corregir" in r.json()["detail"]


# --- entregas repetidas (RN-I) ------------------------------------------------------------------------------


def test_confirmar_dos_veces_el_mismo_destino_es_idempotente_y_otro_destino_tras_entregado_es_409(client, llm_falso):
    from tests.test_aceptacion import med, receta, TEXTO_RECETA

    enviar(client, llm_falso, "REC-1", receta([med("losartan", "50 mg")]), texto=TEXTO_RECETA, canal="Consulta_Ambulatoria")
    detalle = client.get("/documentos/REC-1").json()
    assert detalle["estado"] == "ENRUTADO"
    plan = [detalle["resultado"]["enrutamiento"]["destino_principal"], *detalle["resultado"]["enrutamiento"]["destinos_secundarios"]]
    r1 = client.post("/documentos/REC-1/entregar", json={"destino": plan[0]})
    assert r1.status_code == 200, r1.text
    r2 = client.post("/documentos/REC-1/entregar", json={"destino": plan[0]})  # el mismo clic dos veces, incluso si ya cerró
    assert r2.status_code == 200, r2.text
    assert r1.json()["entregas"] == r2.json()["entregas"] and r2.json()["entregas"][plan[0]] is True
    for destino in plan[1:]:
        assert client.post("/documentos/REC-1/entregar", json={"destino": destino}).status_code == 200
    final = client.get("/documentos/REC-1").json()
    assert final["estado"] == "ENTREGADO"
    assert client.post("/documentos/REC-1/entregar", json={"destino": "Cola_Emergencia_Medica"}).status_code in (400, 409)  # otro destino, ya es final
