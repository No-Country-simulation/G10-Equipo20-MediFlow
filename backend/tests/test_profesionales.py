"""RN-A7: verificación del profesional. El pack declara si hay verificación en línea; donde no existe, el valor es
no_aplica y no penaliza el score. La verificación corre contra el padrón de la instalación, y la consulta en el
registro nacional (ReTHUS) queda anotada a mano con fecha y quién la hizo (RN-CO5).
"""
from app.packs.loader import cargar_pack
from app.schemas.resultado import Profesional
from app.services.profesionales import ServicioProfesionales, normalizar_registro
from tests.test_api_revision import enviar
from tests.test_llm import propuesta_caso_1

RETHUS = "https://web.sispro.gov.co/THS/Cliente/ConsultasPublicas/ConsultaPublicaDeTHxIdentificacion.aspx"


def alta(admin, registro="RM 45678", nombre="Andrés Rojas", **extra):
    return admin.post("/administracion/profesionales", json={"registro": registro, "nombre": nombre, **extra})


# --- regla pura -------------------------------------------------------------------------------------


def test_el_registro_se_compara_sin_prefijo_ni_puntos():
    assert normalizar_registro("RM 45.678") == "45678" == normalizar_registro("45678") == normalizar_registro(" rm-45678 ")
    assert normalizar_registro("TP 1234") == "1234" and normalizar_registro(None) == ""


def test_sin_verificacion_en_linea_en_el_pack_el_valor_es_no_aplica_RN_A7(session):
    pack = cargar_pack("CO")
    sin_linea = pack.model_copy(update={"identidad_profesional": pack.identidad_profesional.model_copy(
        update={"verificacion_en_linea": pack.identidad_profesional.verificacion_en_linea.model_copy(update={"disponible": False})})})
    v = ServicioProfesionales(session, sin_linea).verificar(Profesional(nombre="Andrés Rojas", registro_profesional="45678"))
    assert v.estado == "no_aplica" and v.enlace_consulta is None


def test_la_verificacion_contra_el_padron_distingue_cada_caso(session, admin):
    servicio = ServicioProfesionales(session, cargar_pack("CO"))
    assert servicio.verificar(Profesional(nombre="Andrés Rojas")).estado == "sin_datos"
    assert servicio.verificar(Profesional(nombre="Andrés Rojas", registro_profesional="45678")).estado == "no_encontrado"

    creado = alta(admin, numero_documento="80.123.456").json()
    v = servicio.verificar(Profesional(nombre="Dr. Andrés Rojas", registro_profesional="RM 45.678"))
    assert v.estado == "verificado" and v.fuente == "padrón de profesionales de la instalación" and v.enlace_consulta == RETHUS
    assert "sin consulta en ReTHUS anotada" in v.detalle and v.consultado_en_registro_en is None
    # por documento, cuando el registro no viene
    assert servicio.verificar(Profesional(nombre="Andrés Rojas", numero_documento="80123456")).estado == "verificado"
    # el mismo registro con otro nombre no verifica
    assert servicio.verificar(Profesional(nombre="Carolina Duque", registro_profesional="45678")).estado == "no_encontrado"
    # un profesional inactivo tampoco
    admin.post(f"/administracion/profesionales/{creado['id']}/desactivar")
    assert "inactivo" in servicio.verificar(Profesional(nombre="Andrés Rojas", registro_profesional="45678")).detalle


# --- padrón por la API --------------------------------------------------------------------------------


def test_el_administrador_mantiene_el_padron_y_anota_la_consulta_en_rethus(client, admin, gestor):
    assert alta(gestor).status_code == 403  # RN-K2: administra el administrador
    assert alta(client).status_code == 403
    r = alta(admin, profesion="Medicina", tipo_documento="cc", numero_documento="80.123.456")
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["registro"] == "45678" and p["tipo_documento"] == "CC" and p["numero_documento"] == "80123456" and p["activo"] is True
    assert p["creado_por"] == "admin.root" and p["registro_consultado_en"] is None
    assert alta(admin, registro="45.678", nombre="Otro").status_code == 409
    assert alta(admin, registro="  ", nombre="Otro").status_code == 422
    assert alta(admin, registro="99", nombre="  ").status_code == 422

    r = admin.post(f"/administracion/profesionales/{p['id']}/consulta_registro")
    assert r.status_code == 200 and r.json()["registro_consultado_por"] == "admin.root" and r.json()["registro_consultado_en"]
    assert admin.post("/administracion/profesionales/9999/consulta_registro").status_code == 404
    assert [x["registro"] for x in admin.get("/administracion/profesionales").json()] == ["45678"]
    assert client.get("/administracion/profesionales").status_code == 403  # el padrón vive en administración


# --- en el triaje -------------------------------------------------------------------------------------


def test_RN_A7_el_resultado_dice_si_el_profesional_esta_verificado_y_nunca_penaliza(client, llm_falso, admin):
    enviar(client, llm_falso, "DOC-SIN")
    r = client.get("/documentos/DOC-SIN").json()
    assert r["estado"] == "ENRUTADO"  # no encontrado en el padrón no manda a revisión ni baja el score
    v = r["resultado"]["extraccion"]["profesional"]["verificacion"]
    assert v["estado"] == "no_encontrado" and v["enlace_consulta"] == RETHUS and "45678" in v["detalle"]
    assert [d for d in r["resultado"]["historial_decisiones"] if d["regla"] == "RN-A7"][0]["decision"] == "profesional no_encontrado"

    p = alta(admin).json()
    admin.post(f"/administracion/profesionales/{p['id']}/consulta_registro")
    enviar(client, llm_falso, "DOC-CON", texto="Paciente: Carlos Eduardo Mendes, 52 años. Fecha: 04/04/2026. TC de tórax: TEP agudo. Dr. Andrés Rojas, RM 45678.")
    v = client.get("/documentos/DOC-CON").json()["resultado"]["extraccion"]["profesional"]["verificacion"]
    assert v["estado"] == "verificado" and "ReTHUS consultado el" in v["detalle"] and v["consultado_en_registro_en"]

    p2 = propuesta_caso_1()
    p2["extraccion"]["profesional"] = {"nombre": None, "registro_profesional": None, "tipo_documento": None, "numero_documento": None}
    enviar(client, llm_falso, "DOC-NADA", propuesta=p2, texto="Fecha: 05/04/2026. TC de tórax: TEP agudo. Sin firma.")
    assert client.get("/documentos/DOC-NADA").json()["resultado"]["extraccion"]["profesional"]["verificacion"]["estado"] == "sin_datos"
