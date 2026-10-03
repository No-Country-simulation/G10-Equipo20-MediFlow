"""Cuentas con clave y sesiones (RN-K5), firma con la cuenta (RN-G4, RN-Q5) y acceso por rol (RN-K2).

No hay modo sin sesión: nada se consulta ni se firma sin iniciar sesión. Las cuentas las crea el administrador y
una clave que puso otra persona se cambia en el primer ingreso. `client` es la sesión del auditor aud.ana (conftest).
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.sesiones import COOKIE, clave_coincide, hash_clave
from app.models.gobierno import SesionUsuario, Usuario
from scripts.crear_administrador import crear_administrador
from tests.conftest import crear_cuenta
from tests.test_aceptacion import med, receta, sample, TEXTO_RECETA
from tests.test_api_farmacia_autorizaciones import enviar
from tests.test_llm import propuesta_caso_1

CLAVE = "turno-noche-2026"
CLAVE_DEFINITIVA = "turno-noche-definitiva-2026"


def crear(admin, usuario, rol, clave=CLAVE, tipo="persona"):
    cuerpo = {"usuario": usuario, "nombre": usuario.title(), "rol": rol, "tipo": tipo}
    if clave:
        cuerpo["clave"] = clave
    r = admin.post("/administracion/usuarios", json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


def ingresar(navegador, usuario, clave=CLAVE):
    r = navegador.post("/auth/ingresar", json={"usuario": usuario, "clave": clave})
    if r.status_code == 200 and r.json().get("debe_cambiar_clave"):
        # Una clave puesta por el administrador se cambia en el primer ingreso: aquí la persona elige la suya.
        assert navegador.post("/auth/clave", json={"clave_actual": clave, "clave_nueva": CLAVE_DEFINITIVA}).status_code == 200
    return r


def enviar_tep(client, llm_falso, documento_id):
    enviar(client, llm_falso, documento_id, sample("caso01_tc_torax_tep.txt") + f"\nRef. interna {documento_id}",
           {**propuesta_caso_1(), "extraccion": {**propuesta_caso_1()["extraccion"],
                                                 "paciente": {"nombre": "[PACIENTE_1]", "edad": 52, "sexo": None, "documento": {"tipo": None, "valor": None}}}},
           canal="Guardia_Emergencias")


def sesiones_de(session, usuario):
    return session.query(SesionUsuario).join(Usuario, SesionUsuario.usuario_id == Usuario.id).filter(Usuario.usuario == usuario)


# --- Clave -----------------------------------------------------------------------------------


def test_la_clave_se_guarda_como_hash_con_sal_propia():
    a, b = hash_clave(CLAVE), hash_clave(CLAVE)
    assert a != b and CLAVE not in a and a.startswith("pbkdf2_sha256$")
    assert clave_coincide(CLAVE, a) and clave_coincide(CLAVE, b)
    assert not clave_coincide("otra-clave", a)
    assert not clave_coincide(CLAVE, None) and not clave_coincide(CLAVE, "texto-sin-formato")


def test_la_api_nunca_devuelve_la_clave_ni_su_hash(admin):
    creado = crear(admin, "aud.lucia", "auditor_clinico")
    assert creado["con_clave"] is True and "clave" not in creado and "clave_hash" not in creado
    assert crear(admin, "aud.luis", "auditor_clinico", clave=None)["con_clave"] is False
    assert "pbkdf2" not in admin.get("/administracion/usuarios").text
    corta = admin.post("/administracion/usuarios", json={"usuario": "x", "nombre": "X", "rol": "gestor", "clave": "1234"})
    assert corta.status_code == 422


# --- Inicio y cierre de sesión ---------------------------------------------------------------


def test_ingresar_abre_una_sesion_en_cookie_httponly(admin, anonimo):
    crear(admin, "aud.lucia", "auditor_clinico")
    assert anonimo.get("/auth/estado").json()["sesion"] is None
    r = anonimo.post("/auth/ingresar", json={"usuario": "aud.lucia", "clave": CLAVE})
    assert r.status_code == 200, r.text
    assert r.json() == {"usuario": "aud.lucia", "nombre": "Aud.Lucia", "rol": "auditor_clinico", "debe_cambiar_clave": True}
    cookie = r.headers["set-cookie"]
    assert COOKIE in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    assert anonimo.get("/auth/estado").json()["sesion"]["usuario"] == "aud.lucia"


def test_credenciales_malas_dan_el_mismo_mensaje_sin_revelar_el_motivo(admin, anonimo):
    crear(admin, "aud.lucia", "auditor_clinico")
    crear(admin, "sin.clave", "auditor_clinico", clave=None)
    crear(admin, "ex.empleado", "auditor_clinico")
    admin.post("/administracion/usuarios/ex.empleado/desactivar")
    respuestas = [ingresar(anonimo, "aud.lucia", "equivocada"), ingresar(anonimo, "no.existe"), ingresar(anonimo, "sin.clave"), ingresar(anonimo, "ex.empleado")]
    assert {r.status_code for r in respuestas} == {401}
    assert {r.json()["detail"] for r in respuestas} == {"Usuario o clave incorrectos"}
    assert anonimo.get("/auth/estado").json()["sesion"] is None


def test_salir_cierra_la_sesion_en_el_servidor(admin, anonimo, session):
    crear(admin, "aud.lucia", "auditor_clinico")
    ingresar(anonimo, "aud.lucia")
    assert sesiones_de(session, "aud.lucia").count() == 1
    assert anonimo.post("/auth/salir").json() == {"sesion": None}
    assert sesiones_de(session, "aud.lucia").count() == 0
    assert anonimo.get("/auth/estado").json()["sesion"] is None


def test_una_sesion_vencida_no_sirve(admin, anonimo, session):
    crear(admin, "aud.lucia", "auditor_clinico")
    ingresar(anonimo, "aud.lucia")
    sesiones_de(session, "aud.lucia").one().expira_en = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.commit()
    assert anonimo.get("/auth/estado").json()["sesion"] is None
    assert sesiones_de(session, "aud.lucia").count() == 0


# --- Firma (RN-G4, RN-Q5, RN-K5) -------------------------------------------------------------


def test_RN_Q5_el_acuse_lo_firma_la_cuenta_de_la_sesion(client, llm_falso, jefe):
    enviar_tep(client, llm_falso, "TEP-1")
    r = jefe.post("/alertas/TEP-1/acuse", json={"usuario": "otro.nombre"})  # lo que venga escrito no cuenta
    assert r.status_code == 200, r.text
    assert r.json()["acusado_por"] == "jefe.rojas"


def test_RN_K5_sin_sesion_nadie_firma_ni_consulta(client, anonimo, llm_falso):
    enviar_tep(client, llm_falso, "TEP-1")
    assert anonimo.post("/alertas/TEP-1/acuse", json={"usuario": "jefe.rojas"}).status_code == 401
    assert anonimo.get("/documentos/TEP-1").status_code == 401
    assert client.get("/documentos/TEP-1").json()["alerta"]["estado_acuse"] == "pendiente"


def test_el_rol_es_el_de_la_cuenta_no_el_que_venga_escrito(client, llm_falso, quimico):
    p = receta([med("losartan", "50 mg")])
    p["confianzas"]["medicamento_dosis"] = 0.5
    enviar(client, llm_falso, "REC-DUDA", TEXTO_RECETA, p)
    r = quimico.post("/revision/REC-DUDA/resolver", json={"accion": "aprobar", "usuario": "aud.ana", "rol": "auditor_clinico", "motivo": "ok"})
    assert r.status_code == 403 and "RN-K2" in r.json()["detail"]
    assert client.get("/documentos/REC-DUDA").json()["estado"] == "EN_REVISION_HUMANA"


def test_RN_K3_el_acceso_se_atribuye_a_la_cuenta(client, admin, llm_falso):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    client.get("/documentos/REC-1", headers={"X-Usuario": "otro.nombre"})  # ninguna cabecera cambia quién accede
    accesos = admin.get("/administracion/accesos", params={"documento_id": "REC-1"}).json()
    assert [a["usuario"] for a in accesos] == ["aud.ana"]


# --- Acceso por rol (RN-K2) --------------------------------------------------------------------


@pytest.mark.parametrize("rol, permitidas, negadas", [
    ("auditor_clinico", ["/documentos", "/revision", "/alertas", "/pacientes", "/resumen"], ["/configuracion", "/metricas", "/administracion/usuarios"]),
    ("quimico_farmaceutico", ["/documentos", "/farmacia", "/resumen"], ["/pacientes", "/configuracion", "/administracion/usuarios"]),
    ("gestor", ["/configuracion", "/metricas", "/resumen"], ["/documentos", "/revision", "/pacientes", "/administracion/usuarios"]),
    ("administrador", ["/administracion/usuarios", "/administracion/accesos", "/resumen"], ["/documentos", "/pacientes", "/farmacia", "/configuracion"]),
])
def test_RN_K2_cada_seccion_la_ve_solo_su_rol(como, rol, permitidas, negadas):
    navegador = como("persona.x", rol)
    for ruta in permitidas:
        assert navegador.get(ruta).status_code == 200, ruta
    for ruta in negadas:
        r = navegador.get(ruta)
        assert r.status_code == 403 and "RN-K2" in r.json()["detail"], ruta


def test_nada_se_consulta_ni_se_firma_sin_sesion_RN_K5(client, anonimo, admin, llm_falso):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    for ruta in ("/documentos", "/documentos/REC-1", "/revision", "/pacientes", "/configuracion", "/metricas", "/administracion/usuarios", "/resumen"):
        r = anonimo.get(ruta)
        assert r.status_code == 401 and r.json()["detail"] == "sesion_requerida", ruta
    assert anonimo.post("/documentos", json={"documento_id": "X", "canal_origen": "Externo", "tipo_contenido": "texto", "contenido_texto": "hola"}).status_code == 401
    assert anonimo.post("/farmacia/REC-1/verificar").status_code == 401
    assert anonimo.get("/health").status_code == 200
    assert anonimo.get("/auth/estado").json()["sesion"] is None

    crear(admin, "aud.lucia", "auditor_clinico")
    assert ingresar(anonimo, "aud.lucia").status_code == 200
    assert anonimo.get("/documentos/REC-1").status_code == 200


# --- Efecto inmediato (RN-K4) ----------------------------------------------------------------


def test_RN_K4_desactivar_una_cuenta_cierra_sus_sesiones_abiertas(client, llm_falso, admin, como):
    turno = como("jefe.turno", "jefe_urgencias")
    enviar_tep(client, llm_falso, "TEP-1")
    assert admin.post("/administracion/usuarios/jefe.turno/desactivar").status_code == 200
    assert turno.get("/auth/estado").json()["sesion"] is None
    assert turno.post("/alertas/TEP-1/acuse").status_code == 401
    assert client.get("/documentos/TEP-1").json()["alerta"]["estado_acuse"] == "pendiente"


def test_cambiar_la_clave_cierra_las_sesiones_y_la_anterior_deja_de_servir(admin, anonimo):
    crear(admin, "aud.lucia", "auditor_clinico")
    ingresar(anonimo, "aud.lucia")
    r = admin.post("/administracion/usuarios/aud.lucia/clave", json={"clave": "clave-nueva-2026"})
    assert r.status_code == 200 and r.json()["con_clave"] is True
    assert anonimo.get("/auth/estado").json()["sesion"] is None
    assert ingresar(anonimo, "aud.lucia").status_code == 401
    assert ingresar(anonimo, "aud.lucia", CLAVE_DEFINITIVA).status_code == 401
    assert ingresar(anonimo, "aud.lucia", "clave-nueva-2026").status_code == 200
    assert admin.post("/administracion/usuarios/no.existe/clave", json={"clave": "clave-nueva-2026"}).status_code == 404


def test_solo_un_administrador_crea_cuentas(client, anonimo):
    cuerpo = {"usuario": "x.y", "nombre": "X", "rol": "gestor"}
    assert client.post("/administracion/usuarios", json=cuerpo).status_code == 403  # el auditor clínico no administra
    assert anonimo.post("/administracion/usuarios", json=cuerpo).status_code == 401  # sin sesión, nada


# --- Primera cuenta de administrador por script ----------------------------------------------


def test_crear_administrador_crea_la_primera_cuenta_y_no_pisa_una_existente(session, anonimo):
    assert crear_administrador(session, "admin", "clave-inicial-2026") == "creada"
    cuenta = session.query(Usuario).filter_by(usuario="admin").one()
    assert cuenta.rol == "administrador" and clave_coincide("clave-inicial-2026", cuenta.clave_hash)
    assert crear_administrador(session, "admin", "otra-clave-2027") == "ya_existe"
    assert clave_coincide("clave-inicial-2026", cuenta.clave_hash)  # no se cambia la clave en silencio
    assert ingresar(anonimo, "admin", "clave-inicial-2026").status_code == 200
    with pytest.raises(ValueError, match="al menos"):
        crear_administrador(session, "otro", "corta")
    crear_cuenta(session, "aud.lucia", "auditor_clinico")
    with pytest.raises(ValueError, match="ya existe con el rol"):
        crear_administrador(session, "aud.lucia", "clave-inicial-2026")
