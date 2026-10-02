"""Roles como datos y cuentas generadas por el backend (tabla K; RN-K1, RN-K2, RN-K5, RN-S3).

Los seis roles de la tabla K viven en la tabla `roles`, sembrada por migración: qué secciones ve cada uno,
qué acciones ejecuta y cómo se comporta su pantalla. El frontend arma el menú desde la API, no desde código.
Las cuentas de demostración las genera el backend con todos sus atributos y clave, y cada una inicia sesión.
"""
import pytest
from sqlalchemy import select

from app.core import sesiones
from app.core.config import get_settings
from app.models.gobierno import Usuario
from app.services.roles_base import ROLES_BASE
from app.services.semillas import CUENTAS_DEMO, sembrar_cuentas_demo, sembrar_roles
from app.services.usuarios import ServicioUsuarios

IDS = ["auditor_clinico", "quimico_farmaceutico", "auditor_autorizaciones", "jefe_urgencias", "gestor", "administrador"]


@pytest.fixture(autouse=True)
def hash_rapido(monkeypatch):
    monkeypatch.setattr(sesiones, "ITERACIONES", 1_000)


def test_la_tabla_de_roles_se_siembra_con_los_seis_de_la_tabla_K(session):
    assert sembrar_roles(session) == 6
    assert sembrar_roles(session) == 0  # idempotente
    roles = ServicioUsuarios(session).roles()
    assert [r.id for r in roles] == IDS
    auditor = next(r for r in roles if r.id == "auditor_clinico")
    assert auditor.ve_documentos and "resolver_revision" in auditor.acciones and "revision" in auditor.secciones
    gestor = next(r for r in roles if r.id == "gestor")
    assert not gestor.ve_documentos and gestor.acciones == ["configurar"] and "revision" not in gestor.secciones  # RN-K2
    administrador = next(r for r in roles if r.id == "administrador")
    assert administrador.acciones == ["administrar"] and not administrador.ve_documentos  # RN-K2: nada clínico
    jefe = next(r for r in roles if r.id == "jefe_urgencias")
    assert jefe.pantalla_compartida and jefe.modo_discreto and jefe.alto_contraste


def test_la_base_de_roles_es_la_misma_para_la_migracion_y_la_siembra():
    assert [r["id"] for r in ROLES_BASE] == IDS
    for rol in ROLES_BASE:
        assert {"id", "nombre", "descripcion", "ve", "puede", "secciones", "acciones", "ve_documentos", "ruta_inicial"} <= set(rol)


def test_las_acciones_por_rol_salen_de_la_tabla_RN_K1(session):
    servicio = ServicioUsuarios(session)
    assert servicio.roles_de_accion("verificar_receta") == {"quimico_farmaceutico"}
    assert servicio.roles_de_accion("acusar_alerta") == {"jefe_urgencias", "auditor_clinico"}
    assert servicio.roles_de_accion("configurar") == {"gestor"}
    assert servicio.roles_de_accion("accion_inexistente") == set()


def test_get_auth_roles_es_publico_y_describe_cada_rol_para_el_frontend(client):
    r = client.get("/auth/roles")
    assert r.status_code == 200
    roles = r.json()
    assert [x["id"] for x in roles] == IDS
    jefe = next(x for x in roles if x["id"] == "jefe_urgencias")
    assert {"id", "nombre", "descripcion", "secciones", "acciones", "ve_documentos", "ruta_inicial", "modo_discreto", "alto_contraste", "pantalla_compartida"} <= set(jefe)
    assert jefe["secciones"] == ["inicio", "alertas", "documentos"]
    assert jefe["pantalla_compartida"] is True


def test_las_cuentas_de_demostracion_se_generan_con_todos_sus_atributos_y_clave(session):
    creadas = sembrar_cuentas_demo(session, clave="Demo.2026")
    assert sorted(creadas) == sorted(u for u, _ in CUENTAS_DEMO)
    assert len(CUENTAS_DEMO) == 6 and {rol for _, rol in CUENTAS_DEMO} == set(IDS)  # una por rol
    for cuenta in session.scalars(select(Usuario)).all():
        assert cuenta.clave_hash and sesiones.clave_coincide("Demo.2026", cuenta.clave_hash)
        assert cuenta.activo and cuenta.tipo == "persona" and cuenta.nombre and cuenta.creado_por == "instalacion"
        assert cuenta.rol in IDS and cuenta.ultimo_ingreso_en is None
    assert sembrar_cuentas_demo(session, clave="Demo.2026") == []  # idempotente: no pisa claves cambiadas


def test_cada_cuenta_generada_inicia_sesion_en_la_api_y_recibe_su_rol(client, session):
    sembrar_cuentas_demo(session, clave="Demo.2026")
    for usuario, rol in CUENTAS_DEMO:
        r = client.post("/auth/ingresar", json={"usuario": usuario, "clave": "Demo.2026"})
        assert r.status_code == 200, usuario
        assert r.json()["rol"] == rol and r.json()["usuario"] == usuario and r.json()["nombre"]
        assert client.get("/auth/estado").json()["sesion"]["rol"] == rol
        client.post("/auth/salir")
    cuenta = session.scalars(select(Usuario).where(Usuario.usuario == CUENTAS_DEMO[0][0])).one()
    session.refresh(cuenta)
    assert cuenta.ultimo_ingreso_en is not None


def test_el_arranque_siembra_roles_y_cuentas_cuando_la_instalacion_lo_pide(session, monkeypatch):
    from app.core.arranque import preparar_instalacion

    monkeypatch.setattr(get_settings(), "cuentas_demo", True)
    monkeypatch.setattr(get_settings(), "cuentas_demo_clave", "Demo.2026")
    informe = preparar_instalacion(session)
    assert informe == {"roles": 6, "cuentas": 6}
    assert preparar_instalacion(session) == {"roles": 0, "cuentas": 0}
    monkeypatch.setattr(get_settings(), "cuentas_demo", False)
    assert preparar_instalacion(session) == {"roles": 0, "cuentas": 0}


def test_crear_un_usuario_exige_un_rol_de_la_tabla(client):
    r = client.post("/administracion/usuarios", json={"usuario": "x", "nombre": "X", "rol": "superusuario", "tipo": "persona", "actor": "admin.root"})
    assert r.status_code == 422
    assert "rol desconocido" in r.json()["detail"]
