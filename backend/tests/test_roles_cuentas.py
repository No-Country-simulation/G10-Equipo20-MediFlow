"""Roles como datos (tabla K; RN-K1, RN-K2).

Los seis roles de la tabla K viven en la tabla `roles`, sembrada por migración: qué secciones ve cada uno,
qué acciones ejecuta y cómo se comporta su pantalla. El frontend arma el menú desde la API, no desde código.
"""
import pytest
from app.services.roles_base import ROLES_BASE
from app.services.semillas import sembrar_roles
from app.services.usuarios import ServicioUsuarios

IDS = ["auditor_clinico", "quimico_farmaceutico", "auditor_autorizaciones", "jefe_urgencias", "gestor", "administrador"]


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


def test_el_arranque_siembra_los_roles_y_no_crea_ninguna_cuenta(session):
    """Las cuentas las crea la instalación: la primera desde el ingreso (RN-S3), las demás el administrador (RN-K5)."""
    from app.core.arranque import preparar_instalacion
    from app.models.gobierno import Usuario

    assert preparar_instalacion(session) == {"roles": 6, "tipos_completados": 0}
    assert preparar_instalacion(session) == {"roles": 0, "tipos_completados": 0}
    assert session.query(Usuario).count() == 0


def test_crear_un_usuario_exige_un_rol_de_la_tabla(admin):
    r = admin.post("/administracion/usuarios", json={"usuario": "x", "nombre": "X", "rol": "superusuario", "tipo": "persona"})
    assert r.status_code == 422
    assert "rol desconocido" in r.json()["detail"]
