"""Cuentas con clave y sesiones (RN-K5), firma con la cuenta (RN-G4, RN-Q5) y acceso por rol (RN-K2).

Sin EXIGIR_SESION la instalación sigue en modo demostración: quien no tiene cuenta con clave firma con su nombre.
Una cuenta con clave solo firma con su sesión, y con sesión cada sección la ve solo el rol que la necesita.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core import sesiones
from app.core.config import get_settings
from app.core.sesiones import COOKIE, clave_coincide, hash_clave
from app.main import app
from app.models.gobierno import SesionUsuario, Usuario
from scripts.crear_administrador import crear_administrador
from tests.test_aceptacion import med, receta, sample, TEXTO_RECETA
from tests.test_api_farmacia_autorizaciones import enviar
from tests.test_llm import propuesta_caso_1

ADMIN = {"actor": "admin.root"}
CLAVE = "turno-noche-2026"


@pytest.fixture(autouse=True)
def hash_rapido(monkeypatch):
    monkeypatch.setattr(sesiones, "ITERACIONES", 1_000)


@pytest.fixture
def anonimo(client):
    """Otro navegador contra la misma instalación: no comparte cookies con `client`."""
    with TestClient(app) as otro:
        yield otro


def crear(client, usuario, rol, clave=CLAVE, tipo="persona"):
    cuerpo = {"usuario": usuario, "nombre": usuario.title(), "rol": rol, "tipo": tipo, **ADMIN}
    if clave:
        cuerpo["clave"] = clave
    r = client.post("/administracion/usuarios", json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


def ingresar(client, usuario, clave=CLAVE):
    return client.post("/auth/ingresar", json={"usuario": usuario, "clave": clave})


def enviar_tep(client, llm_falso, documento_id):
    enviar(client, llm_falso, documento_id, sample("caso01_tc_torax_tep.txt") + f"\nRef. interna {documento_id}",
           {**propuesta_caso_1(), "extraccion": {**propuesta_caso_1()["extraccion"],
                                                 "paciente": {"nombre": "[PACIENTE_1]", "edad": 52, "sexo": None, "documento": {"tipo": None, "valor": None}}}},
           canal="Guardia_Emergencias")


# --- Clave -----------------------------------------------------------------------------------


def test_la_clave_se_guarda_como_hash_con_sal_propia():
    a, b = hash_clave(CLAVE), hash_clave(CLAVE)
    assert a != b and CLAVE not in a and a.startswith("pbkdf2_sha256$")
    assert clave_coincide(CLAVE, a) and clave_coincide(CLAVE, b)
    assert not clave_coincide("otra-clave", a)
    assert not clave_coincide(CLAVE, None) and not clave_coincide(CLAVE, "texto-sin-formato")


def test_la_api_nunca_devuelve_la_clave_ni_su_hash(client):
    creado = crear(client, "aud.ana", "auditor_clinico")
    assert creado["con_clave"] is True and "clave" not in creado and "clave_hash" not in creado
    assert crear(client, "aud.luis", "auditor_clinico", clave=None)["con_clave"] is False
    assert "pbkdf2" not in client.get("/administracion/usuarios").text
    corta = client.post("/administracion/usuarios", json={"usuario": "x", "nombre": "X", "rol": "gestor", "clave": "1234", **ADMIN})
    assert corta.status_code == 422


# --- Inicio y cierre de sesión ---------------------------------------------------------------


def test_ingresar_abre_una_sesion_en_cookie_httponly(client):
    crear(client, "aud.ana", "auditor_clinico")
    assert client.get("/auth/estado").json() == {"exigir_sesion": False, "sesion": None}
    r = ingresar(client, "aud.ana")
    assert r.status_code == 200, r.text
    assert r.json() == {"usuario": "aud.ana", "nombre": "Aud.Ana", "rol": "auditor_clinico"}
    cookie = r.headers["set-cookie"]
    assert COOKIE in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    assert client.get("/auth/estado").json()["sesion"]["usuario"] == "aud.ana"


def test_credenciales_malas_dan_el_mismo_mensaje_sin_revelar_el_motivo(client):
    crear(client, "aud.ana", "auditor_clinico")
    crear(client, "sin.clave", "auditor_clinico", clave=None)
    crear(client, "ex.empleado", "auditor_clinico")
    client.post("/administracion/usuarios/ex.empleado/desactivar", json=ADMIN)
    respuestas = [ingresar(client, "aud.ana", "equivocada"), ingresar(client, "no.existe"), ingresar(client, "sin.clave"), ingresar(client, "ex.empleado")]
    assert {r.status_code for r in respuestas} == {401}
    assert {r.json()["detail"] for r in respuestas} == {"Usuario o clave incorrectos"}
    assert client.get("/auth/estado").json()["sesion"] is None


def test_salir_cierra_la_sesion_en_el_servidor(client, session):
    crear(client, "aud.ana", "auditor_clinico")
    ingresar(client, "aud.ana")
    assert session.query(SesionUsuario).count() == 1
    assert client.post("/auth/salir").json() == {"sesion": None}
    assert session.query(SesionUsuario).count() == 0
    assert client.get("/auth/estado").json()["sesion"] is None


def test_una_sesion_vencida_no_sirve(client, session):
    crear(client, "aud.ana", "auditor_clinico")
    ingresar(client, "aud.ana")
    session.query(SesionUsuario).one().expira_en = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.commit()
    assert client.get("/auth/estado").json()["sesion"] is None
    assert session.query(SesionUsuario).count() == 0


# --- Firma (RN-G4, RN-Q5, RN-K5) -------------------------------------------------------------


def test_RN_Q5_con_sesion_firma_la_cuenta_y_no_el_nombre_que_venga_escrito(client, llm_falso):
    crear(client, "jefe.rojas", "jefe_urgencias")
    enviar_tep(client, llm_falso, "TEP-1")
    ingresar(client, "jefe.rojas")
    r = client.post("/alertas/TEP-1/acuse", json={"usuario": "otro.nombre"})
    assert r.status_code == 200, r.text
    assert r.json()["acusado_por"] == "jefe.rojas"


def test_RN_K5_una_cuenta_con_clave_no_se_usa_escribiendo_su_nombre(client, anonimo, llm_falso):
    crear(client, "jefe.rojas", "jefe_urgencias")
    crear(client, "jefe.sin.clave", "jefe_urgencias", clave=None)
    enviar_tep(client, llm_falso, "TEP-1")
    suplantado = anonimo.post("/alertas/TEP-1/acuse", json={"usuario": "jefe.rojas"})
    assert suplantado.status_code == 401 and "RN-K5" in suplantado.json()["detail"]
    assert anonimo.get("/documentos/TEP-1").json()["alerta"]["estado_acuse"] == "pendiente"
    # modo demostración: quien no tiene clave sigue firmando con su nombre
    assert anonimo.post("/alertas/TEP-1/acuse", json={"usuario": "jefe.sin.clave"}).status_code == 200


def test_con_sesion_el_rol_es_el_de_la_cuenta_no_el_declarado(client, llm_falso):
    crear(client, "qf.maria", "quimico_farmaceutico")
    p = receta([med("losartan", "50 mg")])
    p["confianzas"]["medicamento_dosis"] = 0.5
    enviar(client, llm_falso, "REC-DUDA", TEXTO_RECETA, p)
    ingresar(client, "qf.maria")
    r = client.post("/revision/REC-DUDA/resolver", json={"accion": "aprobar", "usuario": "qf.maria", "rol": "auditor_clinico", "motivo": "ok"})
    assert r.status_code == 403 and "RN-K2" in r.json()["detail"]
    assert client.get("/documentos/REC-DUDA").json()["estado"] == "EN_REVISION_HUMANA"


def test_RN_K3_con_sesion_el_acceso_se_atribuye_a_la_cuenta(client, anonimo, llm_falso):
    crear(client, "aud.ana", "auditor_clinico")
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    ingresar(client, "aud.ana")
    client.get("/documentos/REC-1", headers={"X-Usuario": "otro.nombre"})
    accesos = anonimo.get("/administracion/accesos", params={"documento_id": "REC-1"}).json()
    assert [a["usuario"] for a in accesos] == ["aud.ana"]


# --- Acceso por rol con sesión (RN-K2) -------------------------------------------------------


@pytest.mark.parametrize("rol, permitidas, negadas", [
    ("auditor_clinico", ["/documentos", "/revision", "/alertas", "/pacientes", "/resumen"], ["/configuracion", "/metricas", "/administracion/usuarios"]),
    ("quimico_farmaceutico", ["/documentos", "/farmacia", "/resumen"], ["/pacientes", "/configuracion", "/administracion/usuarios"]),
    ("gestor", ["/configuracion", "/metricas", "/resumen"], ["/documentos", "/revision", "/pacientes", "/administracion/usuarios"]),
    ("administrador", ["/administracion/usuarios", "/administracion/accesos", "/resumen"], ["/documentos", "/pacientes", "/farmacia", "/configuracion"]),
])
def test_RN_K2_con_sesion_cada_seccion_la_ve_solo_su_rol(client, rol, permitidas, negadas):
    crear(client, "persona.x", rol)
    ingresar(client, "persona.x")
    for ruta in permitidas:
        assert client.get(ruta).status_code == 200, ruta
    for ruta in negadas:
        r = client.get(ruta)
        assert r.status_code == 403 and "RN-K2" in r.json()["detail"], ruta


# --- Instalación con sesión obligatoria ------------------------------------------------------


def test_EXIGIR_SESION_nada_se_consulta_ni_se_firma_sin_sesion(client, anonimo, llm_falso, monkeypatch):
    crear(client, "aud.ana", "auditor_clinico")
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    monkeypatch.setattr(get_settings(), "exigir_sesion", True)

    for ruta in ("/documentos", "/documentos/REC-1", "/revision", "/pacientes", "/configuracion", "/metricas", "/administracion/usuarios", "/resumen"):
        r = anonimo.get(ruta)
        assert r.status_code == 401 and r.json()["detail"] == "sesion_requerida", ruta
    assert anonimo.post("/documentos", json={"documento_id": "X", "canal_origen": "Externo", "tipo_contenido": "texto", "contenido_texto": "hola"}).status_code == 401
    assert anonimo.post("/farmacia/REC-1/verificar", json={"usuario": "cualquiera"}).status_code == 401
    assert anonimo.get("/health").status_code == 200
    assert anonimo.get("/auth/estado").json() == {"exigir_sesion": True, "sesion": None}

    assert ingresar(anonimo, "aud.ana").status_code == 200
    assert anonimo.get("/documentos/REC-1").status_code == 200


def test_RN_S3_la_puesta_en_marcha_informa_si_la_sesion_es_obligatoria(client, monkeypatch):
    por_clave = {r["clave"]: r for r in client.get("/administracion/puesta_en_marcha").json()["requisitos"]}
    assert por_clave["sesion_obligatoria"]["cumplido"] is False and "EXIGIR_SESION" in por_clave["sesion_obligatoria"]["detalle"]
    crear(client, "admin.root", "administrador")
    ingresar(client, "admin.root")
    monkeypatch.setattr(get_settings(), "exigir_sesion", True)
    por_clave = {r["clave"]: r for r in client.get("/administracion/puesta_en_marcha").json()["requisitos"]}
    assert por_clave["sesion_obligatoria"]["cumplido"] is True


# --- Efecto inmediato (RN-K4) ----------------------------------------------------------------


def test_RN_K4_desactivar_una_cuenta_cierra_sus_sesiones_abiertas(client, anonimo, llm_falso):
    crear(client, "jefe.rojas", "jefe_urgencias")
    enviar_tep(client, llm_falso, "TEP-1")
    ingresar(client, "jefe.rojas")
    assert anonimo.post("/administracion/usuarios/jefe.rojas/desactivar", json=ADMIN).status_code == 200
    assert client.get("/auth/estado").json()["sesion"] is None
    bloqueado = client.post("/alertas/TEP-1/acuse", json={"usuario": "jefe.rojas"})
    assert bloqueado.status_code in (401, 403)
    assert anonimo.get("/documentos/TEP-1").json()["alerta"]["estado_acuse"] == "pendiente"


def test_cambiar_la_clave_cierra_las_sesiones_y_la_anterior_deja_de_servir(client, anonimo):
    crear(client, "aud.ana", "auditor_clinico")
    ingresar(client, "aud.ana")
    r = anonimo.post("/administracion/usuarios/aud.ana/clave", json={"clave": "clave-nueva-2026", **ADMIN})
    assert r.status_code == 200 and r.json()["con_clave"] is True
    assert client.get("/auth/estado").json()["sesion"] is None
    assert ingresar(client, "aud.ana").status_code == 401
    assert ingresar(client, "aud.ana", "clave-nueva-2026").status_code == 200
    assert anonimo.post("/administracion/usuarios/no.existe/clave", json={"clave": "clave-nueva-2026", **ADMIN}).status_code == 404


def test_con_sesion_solo_un_administrador_crea_cuentas(client):
    crear(client, "aud.ana", "auditor_clinico")
    crear(client, "admin.root", "administrador")  # desde aquí, admin.root solo actúa con su sesión
    ingresar(client, "aud.ana")
    assert client.post("/administracion/usuarios", json={"usuario": "x.y", "nombre": "X", "rol": "gestor", **ADMIN}).status_code == 403
    client.post("/auth/salir")
    # sin sesión, el nombre de una cuenta con clave no sirve como actor
    assert client.post("/administracion/usuarios", json={"usuario": "x.y", "nombre": "X", "rol": "gestor", "actor": "admin.root"}).status_code == 401
    ingresar(client, "admin.root")
    creado = client.post("/administracion/usuarios", json={"usuario": "x.y", "nombre": "X", "rol": "gestor", "actor": "lo.que.sea"})
    assert creado.status_code == 201 and creado.json()["creado_por"] == "admin.root"


# --- Primera cuenta de administrador ---------------------------------------------------------


def test_crear_administrador_crea_la_primera_cuenta_y_no_pisa_una_existente(client, session):
    assert crear_administrador(session, "admin", "clave-inicial-larga") == "creada"
    cuenta = session.query(Usuario).filter_by(usuario="admin").one()
    assert cuenta.rol == "administrador" and clave_coincide("clave-inicial-larga", cuenta.clave_hash)
    assert crear_administrador(session, "admin", "otra-clave-distinta") == "ya_existe"
    assert clave_coincide("clave-inicial-larga", cuenta.clave_hash)  # no se cambia la clave en silencio
    assert ingresar(client, "admin", "clave-inicial-larga").status_code == 200
    with pytest.raises(ValueError, match="al menos"):
        crear_administrador(session, "otro", "corta")
    crear(client, "aud.ana", "auditor_clinico")
    with pytest.raises(ValueError, match="ya existe con el rol"):
        crear_administrador(session, "aud.ana", "clave-inicial-larga")
