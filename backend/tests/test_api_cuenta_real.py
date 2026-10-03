"""La instalación como producto (RN-K3, RN-K4, RN-K5, RN-J9, RN-S3, RN-G4).

No existe modo sin sesión. El primer administrador se crea desde la pantalla de ingreso solo mientras no exista
ninguna cuenta; toda clave inicial se cambia en el primer ingreso; los intentos fallidos bloquean la cuenta un rato y
quedan registrados; y cada rol lista y abre solo los tipos de documento que le corresponden.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.api.deps import get_llm, get_memoria, get_session, get_storage
from app.core.config import Settings, get_settings
from app.main import app
from app.models.gobierno import Usuario
from tests.test_aceptacion import med, receta, TEXTO_RECETA
from tests.test_api_farmacia_autorizaciones import enviar
from tests.test_llm import propuesta_caso_1

CLAVE = "turno-noche-2026"
TEXTO_TEP = "Paciente: Carlos Mendes, 52 años. Fecha: 03/04/2026. TC de tórax: tromboembolismo pulmonar agudo. Dr. Rojas, RM 45678."


@pytest.fixture
def instalacion_vacia(session, storage, llm_falso):
    """Un navegador contra una instalación recién instalada: sin ninguna cuenta (RN-S3)."""
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_llm] = lambda: llm_falso
    memoria = InMemorySaver()
    app.dependency_overrides[get_memoria] = lambda: memoria
    with TestClient(app) as navegador:
        yield navegador
    app.dependency_overrides.clear()


def crear(admin, usuario, rol, clave=CLAVE):
    r = admin.post("/administracion/usuarios", json={"usuario": usuario, "nombre": usuario.title(), "rol": rol, "tipo": "persona", "clave": clave})
    assert r.status_code == 201, r.text
    return r.json()


def ingresar(navegador, usuario, clave=CLAVE):
    return navegador.post("/auth/ingresar", json={"usuario": usuario, "clave": clave})


def cambiar_clave(navegador, actual, nueva):
    return navegador.post("/auth/clave", json={"clave_actual": actual, "clave_nueva": nueva})


# --- No hay modo sin sesión ------------------------------------------------------------------------


def test_no_existe_configuracion_para_apagar_la_sesion_ni_cuentas_sembradas_RN_K5():
    ajustes = Settings(_env_file=None)
    assert not hasattr(ajustes, "exigir_sesion")
    assert not hasattr(ajustes, "cuentas_demo")


# --- Primer administrador desde la pantalla de ingreso (RN-S3) ---------------------------------------


def test_sin_cuentas_la_api_lo_dice_y_deja_crear_al_primer_administrador(instalacion_vacia, session):
    assert instalacion_vacia.get("/auth/estado").json()["sin_cuentas"] is True
    r = instalacion_vacia.post("/auth/primer_administrador", json={"usuario": "admin", "nombre": "Administración TI", "clave": "Clave.inicial.2026"})
    assert r.status_code == 201, r.text
    assert r.json() == {"usuario": "admin", "nombre": "Administración TI", "rol": "administrador", "debe_cambiar_clave": False}
    assert instalacion_vacia.get("/auth/estado").json()["sesion"]["usuario"] == "admin"  # entra con sesión abierta
    assert instalacion_vacia.get("/auth/estado").json()["sin_cuentas"] is False
    assert session.query(Usuario).one().creado_por == "instalacion"


def test_el_primer_administrador_solo_existe_mientras_no_haya_cuentas(instalacion_vacia):
    assert instalacion_vacia.post("/auth/primer_administrador", json={"usuario": "admin", "nombre": "TI", "clave": "Clave.inicial.2026"}).status_code == 201
    instalacion_vacia.post("/auth/salir")
    r = instalacion_vacia.post("/auth/primer_administrador", json={"usuario": "otro", "nombre": "Otro", "clave": "Clave.inicial.2026"})
    assert r.status_code == 409


def test_la_clave_tiene_una_politica_minima(instalacion_vacia):
    for mala in ("corta1", "1234567890", "solo-letras-aqui", "admin"):
        r = instalacion_vacia.post("/auth/primer_administrador", json={"usuario": "admin", "nombre": "TI", "clave": mala})
        assert r.status_code == 422, mala
    assert instalacion_vacia.get("/auth/estado").json()["sin_cuentas"] is True


# --- Clave inicial que se cambia en el primer ingreso --------------------------------------------------


def test_una_clave_puesta_por_el_administrador_se_cambia_en_el_primer_ingreso(admin, anonimo):
    creado = crear(admin, "aud.lucia", "auditor_clinico")
    assert creado["debe_cambiar_clave"] is True
    r = ingresar(anonimo, "aud.lucia")
    assert r.status_code == 200 and r.json()["debe_cambiar_clave"] is True
    bloqueado = anonimo.get("/documentos")
    assert bloqueado.status_code == 403 and bloqueado.json()["detail"] == "cambio_de_clave_requerido"
    assert anonimo.get("/auth/estado").json()["sesion"]["debe_cambiar_clave"] is True

    assert cambiar_clave(anonimo, "equivocada", "Nueva.clave.2026").status_code == 401
    assert cambiar_clave(anonimo, CLAVE, "corta1").status_code == 422
    r = cambiar_clave(anonimo, CLAVE, "Nueva.clave.2026")
    assert r.status_code == 200 and r.json()["debe_cambiar_clave"] is False
    assert anonimo.get("/documentos").status_code == 200
    anonimo.post("/auth/salir")
    assert ingresar(anonimo, "aud.lucia", CLAVE).status_code == 401  # la anterior ya no sirve
    assert ingresar(anonimo, "aud.lucia", "Nueva.clave.2026").status_code == 200


def test_cambiar_la_clave_exige_sesion(anonimo):
    assert cambiar_clave(anonimo, "x", "Nueva.clave.2026").status_code == 401


# --- Intentos fallidos y bloqueo (RN-K3, RN-K4) ----------------------------------------------------------


def test_varios_intentos_fallidos_bloquean_la_cuenta_un_rato_con_el_mismo_mensaje(admin, anonimo, session):
    crear(admin, "aud.lucia", "auditor_clinico")
    maximos = get_settings().intentos_maximos
    for _ in range(maximos):
        assert ingresar(anonimo, "aud.lucia", "mala").status_code == 401
    bloqueado = ingresar(anonimo, "aud.lucia", CLAVE)  # clave correcta, cuenta bloqueada
    assert bloqueado.status_code == 401 and bloqueado.json()["detail"] == "Usuario o clave incorrectos"
    cuenta = session.query(Usuario).filter_by(usuario="aud.lucia").one()
    session.refresh(cuenta)
    assert cuenta.bloqueado_hasta is not None
    cuenta.bloqueado_hasta = datetime.now(timezone.utc) - timedelta(minutes=1)  # pasó el bloqueo
    session.commit()
    assert ingresar(anonimo, "aud.lucia", CLAVE).status_code == 200
    session.refresh(cuenta)
    assert cuenta.intentos_fallidos == 0 and cuenta.bloqueado_hasta is None


def test_los_eventos_de_sesion_quedan_registrados_sin_la_clave(admin, anonimo):
    crear(admin, "aud.lucia", "auditor_clinico")
    ingresar(anonimo, "aud.lucia", "mala")
    ingresar(anonimo, "aud.lucia")
    cambiar_clave(anonimo, CLAVE, "Nueva.clave.2026")
    anonimo.post("/auth/salir")
    r = admin.get("/administracion/eventos_sesion")
    assert r.status_code == 200
    eventos = [(e["usuario"], e["evento"]) for e in r.json()]
    assert eventos[:4] == [("aud.lucia", "salida"), ("aud.lucia", "cambio_clave"), ("aud.lucia", "ingreso"), ("aud.lucia", "fallo")]
    assert all(CLAVE not in str(e) and "Nueva.clave" not in str(e) for e in r.json())
    assert all({"usuario", "evento", "detalle", "fecha_hora"} <= set(e) for e in r.json())


def test_la_cookie_es_segura_detras_de_un_proxy_https(admin, anonimo):
    crear(admin, "aud.lucia", "auditor_clinico")
    r = anonimo.post("/auth/ingresar", json={"usuario": "aud.lucia", "clave": CLAVE}, headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 200
    assert "secure" in r.headers["set-cookie"].lower()


# --- Cada rol lista y abre solo lo suyo (RN-J9, RN-K1) ---------------------------------------------------


def _cargar_receta_e_informe(client, llm_falso):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    llm_falso.respuestas.append(propuesta_caso_1())
    r = client.post("/documentos", json={"documento_id": "INF-1", "canal_origen": "Guardia_Emergencias", "tipo_contenido": "texto", "contenido_texto": TEXTO_TEP})
    assert r.status_code == 200, r.text


def test_el_quimico_lista_y_abre_solo_recetas_y_el_auditor_clinico_ve_todo_RN_J9(client, quimico, llm_falso):
    _cargar_receta_e_informe(client, llm_falso)
    ids = [d["documento_id"] for d in quimico.get("/documentos").json()["items"]]
    assert ids == ["REC-1"]
    assert quimico.get("/documentos/REC-1").status_code == 200
    vedado = quimico.get("/documentos/INF-1")
    assert vedado.status_code == 403 and "RN-J9" in vedado.json()["detail"]
    assert quimico.get("/documentos/INF-1/original").status_code == 403
    ids = sorted(d["documento_id"] for d in client.get("/documentos").json()["items"])
    assert ids == ["INF-1", "REC-1"]
    assert client.get("/documentos/INF-1").status_code == 200


def test_el_tipo_del_documento_queda_en_su_fila_para_poder_filtrar(client, llm_falso, session):
    from app.models.documento import Documento

    _cargar_receta_e_informe(client, llm_falso)
    tipos = {d.documento_id: d.tipo for d in session.query(Documento).all()}
    assert tipos == {"REC-1": "Receta Médica", "INF-1": "Informe de Imágenes"}


def test_el_arranque_completa_el_tipo_de_los_documentos_anteriores(client, llm_falso, session):
    from app.core.arranque import preparar_instalacion
    from app.models.documento import Documento

    _cargar_receta_e_informe(client, llm_falso)
    for d in session.query(Documento).all():
        d.tipo = None
    session.commit()
    assert preparar_instalacion(session)["tipos_completados"] == 2
    assert {d.tipo for d in session.query(Documento).all()} == {"Receta Médica", "Informe de Imágenes"}
