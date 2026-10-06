"""RN-L1: el gestor configura la cadena de escalamiento (RN-Q2) y los canales (RN-P7) como una versión más (RN-L4),
con dos aprobadores cuando la cadena pierde niveles o se quita un canal (RN-L5). La cadena nueva rige las alertas nuevas.
"""
import pytest

from app.packs.loader import cargar_umbrales
from app.services.configuracion import (CambiosConfiguracion, ErrorConfiguracion, acumular, aplicar_umbrales, toca_seguridad,
                                        validar_notificaciones)
from tests.test_aceptacion import propuesta, sample
from tests.test_api_configuracion import proponer
from tests.test_api_farmacia_autorizaciones import enviar


def cambios(cadena=None, canales=None) -> CambiosConfiguracion:
    return CambiosConfiguracion(notificaciones={"cadena_guardia": cadena, "canales": canales})


# --- reglas puras -------------------------------------------------------------------------------------


def test_la_cadena_tiene_niveles_sin_repetir_y_los_canales_son_los_que_el_sistema_sabe_usar():
    validar_notificaciones(cambios(cadena=["Jefe de Urgencias", "Dirección Médica"], canales=["Correo", "Slack"]))
    for malo in ([], [" "], ["Jefe", "jefe"], ["x" * 65]):
        with pytest.raises(ErrorConfiguracion, match="RN-Q2"):
            validar_notificaciones(cambios(cadena=malo))
    for malo in ([], ["Paloma"], ["Slack", "Slack"]):
        with pytest.raises(ErrorConfiguracion, match="RN-P7"):
            validar_notificaciones(cambios(canales=malo))
    validar_notificaciones(CambiosConfiguracion())  # sin tocar nada no hay nada que validar


def test_RN_L5_perder_un_nivel_o_un_canal_toca_seguridad_y_reordenar_o_agregar_no():
    base = cargar_umbrales()  # tres niveles, dos canales
    assert toca_seguridad(base, cambios(cadena=["Jefe de Urgencias", "Dirección Médica"])) is True
    assert toca_seguridad(base, cambios(cadena=["Dirección Médica", "Coordinador Médico de Turno", "Jefe de Urgencias"])) is False
    assert toca_seguridad(base, cambios(cadena=[*base.notificaciones.cadena_guardia, "Gerencia"])) is False
    assert toca_seguridad(base, cambios(canales=["Slack"])) is True
    assert toca_seguridad(base, cambios(canales=["Correo", "Slack"])) is False


def test_la_cadena_de_una_version_se_hereda_y_se_aplica_a_los_umbrales():
    v1 = cambios(cadena=["Jefe de Urgencias", "Gerencia"])
    v2 = CambiosConfiguracion(umbrales={"confianza.profesional": 0.9})
    v3 = cambios(canales=["Correo", "Slack"])
    todo = acumular(acumular(v1, v2), v3)
    assert todo.notificaciones.cadena_guardia == ["Jefe de Urgencias", "Gerencia"] and todo.notificaciones.canales == ["Correo", "Slack"]
    efectivos = aplicar_umbrales(cargar_umbrales(), todo)
    assert efectivos.notificaciones.cadena_guardia == ["Jefe de Urgencias", "Gerencia"] and efectivos.notificaciones.canales == ["Correo", "Slack"]
    assert efectivos.notificaciones.slack.criticos == "urgente"  # lo que la versión no toca sigue igual
    assert aplicar_umbrales(cargar_umbrales(), v2).notificaciones.cadena_guardia == cargar_umbrales().notificaciones.cadena_guardia


# --- por la API ---------------------------------------------------------------------------------------


def test_RN_L1_el_gestor_cambia_la_cadena_y_las_alertas_nuevas_la_siguen(client, llm_falso, gestor, gestor2):
    cfg = gestor.get("/configuracion").json()
    assert cfg["notificaciones"]["cadena_guardia"] == ["Jefe de Urgencias", "Coordinador Médico de Turno", "Dirección Médica"]
    assert cfg["notificaciones"]["canales"] == ["Slack", "Correo"] and cfg["notificaciones"]["canales_conocidos"] == ["Slack", "Correo"]

    r = proponer(gestor, {"notificaciones": {"cadena_guardia": ["Médico de Turno", "Jefe de Urgencias", "Dirección Médica"]}}, motivo="turnos nuevos")
    assert r.status_code == 201, r.text
    assert r.json()["toca_seguridad"] is False  # mismos niveles, otro orden
    assert gestor.post(f"/configuracion/propuestas/{r.json()['id']}/aprobar").json()["estado"] == "vigente"
    assert gestor.get("/configuracion").json()["notificaciones"]["cadena_guardia"][0] == "Médico de Turno"

    enviar(client, llm_falso, "TEP-1", sample("caso01_tc_torax_tep.txt"), propuesta(**{"extraccion.paciente.documento": {"tipo": None, "valor": None}}),
           canal="Guardia_Emergencias")
    alerta = client.get("/documentos/TEP-1").json()["alerta"]
    assert alerta["destinatario"] == "Médico de Turno"  # RN-Q2: la cadena vigente decide a quién va la alerta

    # quitar un nivel o un canal toca seguridad: dos aprobadores distintos (RN-L5)
    r = proponer(gestor, {"notificaciones": {"cadena_guardia": ["Jefe de Urgencias"], "canales": ["Slack"]}}, motivo="una sola guardia")
    assert r.status_code == 201 and r.json()["toca_seguridad"] is True and r.json()["aprobaciones_requeridas"] == 2
    assert gestor.post(f"/configuracion/propuestas/{r.json()['id']}/aprobar").json()["estado"] == "propuesta"
    assert gestor2.post(f"/configuracion/propuestas/{r.json()['id']}/aprobar").json()["estado"] == "vigente"
    efectivas = gestor.get("/configuracion").json()["notificaciones"]
    assert efectivas["cadena_guardia"] == ["Jefe de Urgencias"] and efectivas["canales"] == ["Slack"]


def test_las_validaciones_de_la_api_citan_la_regla(gestor):
    assert "RN-Q2" in proponer(gestor, {"notificaciones": {"cadena_guardia": []}}).json()["detail"]
    assert "RN-P7" in proponer(gestor, {"notificaciones": {"canales": ["Paloma"]}}).json()["detail"]
    assert proponer(gestor, {"notificaciones": {"cadena_guardia": None, "canales": None}}).status_code == 422  # RN-L4: sin cambios
