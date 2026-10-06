"""Slack por webhooks (RN-F1, RN-F2, RN-F3, RN-P7, RN-Q2, RN-Q4).

Sin red (RN-U4): el transporte HTTP es simulado. Lo que importa: el mensaje va al canal del rol, no lleva datos del
paciente, la dirección del webhook no aparece en ningún registro, y un fallo es un canal caído que el servicio de
alertas resuelve con el canal alternativo y el escalamiento que ya existían.
"""
import json
import logging
from datetime import timedelta

import httpx
import pytest

from app.api.deps import get_notificador
from app.core.config import get_settings
from app.packs.loader import cargar_umbrales
from app.packs.modelos import Slack
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.resultado import NivelPrioridad as N
from app.services.alertas import CanalCaido, NotificadorFalso, NotificadorRegistro, NotificadorSlack, ServicioAlertas
from app.services.llm import ClienteFalso, ServicioExtraccion
from app.services.orquestador import Orquestador
from tests.fabrica import propuesta as fabricar
from tests.test_aceptacion import med, propuesta, receta, TEXTO_RECETA
from tests.test_api_farmacia_autorizaciones import enviar
from tests.test_grafo import ingresar, request_caso_1
from tests.test_llm import propuesta_caso_1

URGENTE = "https://hooks.slack.com/services/T0/B0/urgente-secreto"
GENERAL = "https://hooks.slack.com/services/T0/B0/general-secreto"


class SlackSimulado:
    """Un Slack que recibe los webhooks: guarda cada publicación y puede caerse o responder con error."""

    def __init__(self, estado: int = 200, caido: bool = False):
        self.estado, self.caido = estado, caido
        self.publicaciones: list[tuple[str, str]] = []  # (url, texto)

    def manejar(self, peticion: httpx.Request) -> httpx.Response:
        if self.caido:
            raise httpx.ConnectTimeout("sin respuesta", request=peticion)
        self.publicaciones.append((str(peticion.url), json.loads(peticion.content)["text"]))
        return httpx.Response(self.estado, text="ok" if self.estado == 200 else "invalid_payload")

    @property
    def cliente(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.manejar))


def notificador(slack: SlackSimulado, config: Slack | None = None, **webhooks) -> NotificadorSlack:
    return NotificadorSlack({"general": GENERAL, "urgente": URGENTE, **webhooks}, config or Slack(), cliente=slack.cliente)


@pytest.fixture
def repo(session):
    return RepositorioDocumentos(session)


def procesar_caso_1(repo, storage, notificador):
    orq = Orquestador(repo, storage, ServicioExtraccion(ClienteFalso(respuestas=[propuesta_caso_1()]), max_intentos=1), notificador=notificador)
    doc = ingresar(repo, storage, request_caso_1())
    orq.procesar(doc)
    return doc


# --- Mensaje ------------------------------------------------------------------------------------


def test_la_alerta_critica_va_al_canal_de_guardia_con_mencion_destinatario_y_enlace_RN_F1_RN_Q2(repo, storage):
    slack = SlackSimulado()
    doc = procesar_caso_1(repo, storage, notificador(slack))
    alerta = repo.alerta_activa(doc)
    assert (alerta.canal, alerta.destinatario, alerta.escalamientos) == ("Slack", "Jefe de Urgencias", [])
    assert len(slack.publicaciones) == 1
    url, texto = slack.publicaciones[0]
    assert url == URGENTE
    assert texto.startswith("@channel Alerta Crítica. Doc: DOC-CLIN-2026-8942.")
    assert "Para: Jefe de Urgencias." in texto and "|Abrir en MediFlow>" in texto and doc.documento_id in texto


def test_el_mensaje_no_lleva_datos_del_paciente_RN_Q4(repo, storage):
    slack = SlackSimulado()
    procesar_caso_1(repo, storage, notificador(slack))
    _, texto = slack.publicaciones[0]
    for dato in ("Mendes", "Carlos", "52", "tromboembolismo", "Rojas"):
        assert dato not in texto


def test_cada_rol_puede_tener_su_canal_y_sin_mencion_configurada_no_se_menciona():
    slack = SlackSimulado()
    config = Slack(por_rol={"Dirección Médica": "direccion"}, mencion_criticos="")
    n = notificador(slack, config, direccion="https://hooks.slack.com/services/T0/B0/direccion")
    n.enviar("Slack", "Dirección Médica", "Alerta Crítica. Doc: X. Nivel: Crítico. Requiere acuse.", None)
    n.enviar("Slack", "Jefe de Urgencias", "Alerta Crítica. Doc: Y. Nivel: Crítico. Requiere acuse.", None)
    assert [u for u, _ in slack.publicaciones] == ["https://hooks.slack.com/services/T0/B0/direccion", URGENTE]
    assert not slack.publicaciones[0][1].startswith("@")


# --- Canal caído (RN-P7) --------------------------------------------------------------------------


@pytest.mark.parametrize("slack", [SlackSimulado(caido=True), SlackSimulado(estado=500), SlackSimulado(estado=404)])
def test_sin_respuesta_o_con_error_el_canal_cuenta_como_caido(slack):
    with pytest.raises(CanalCaido) as error:
        notificador(slack).enviar("Slack", "Jefe de Urgencias", "Alerta Crítica. Doc: X.", None)
    assert "secreto" not in str(error.value)  # la dirección del webhook no sale en el error


def test_un_canal_que_no_es_slack_o_sin_webhook_cuenta_como_caido():
    n = notificador(SlackSimulado())
    with pytest.raises(CanalCaido):
        n.enviar("Correo", "Jefe de Urgencias", "Alerta Crítica. Doc: X.", None)
    sin_urgente = NotificadorSlack({"general": GENERAL, "urgente": ""}, Slack(), cliente=SlackSimulado().cliente)
    assert sin_urgente.configurado
    with pytest.raises(CanalCaido, match="urgente"):
        sin_urgente.enviar("Slack", "Jefe de Urgencias", "Alerta Crítica. Doc: X.", None)


def test_con_slack_caido_la_cadena_se_agota_y_la_alerta_sigue_en_la_bandeja_RN_P7(repo, storage, caplog):
    slack = SlackSimulado(caido=True)
    with caplog.at_level(logging.WARNING):
        doc = procesar_caso_1(repo, storage, notificador(slack))
    alerta = repo.alerta_activa(doc)
    assert alerta.estado_acuse == "pendiente"
    assert [e["tipo"] for e in alerta.escalamientos] == ["escalamiento", "escalamiento", "sin_canal"]
    assert alerta.destinatario == "Dirección Médica"
    assert slack.publicaciones == []
    assert "secreto" not in caplog.text


# --- Escalamiento (RN-F2) ------------------------------------------------------------------------


def test_el_escalamiento_publica_un_segundo_mensaje_que_nombra_el_cambio_de_rol_RN_F2(repo, storage):
    slack = SlackSimulado()
    n = notificador(slack)
    doc = procesar_caso_1(repo, storage, n)
    alerta = repo.alerta_activa(doc)
    servicio = ServicioAlertas(repo, cargar_umbrales(), n)
    plazo = timedelta(minutes=cargar_umbrales().tiempos.escalamiento_sin_acuse_min)
    assert servicio.escalar_vencidas(ahora=alerta.emitida_en + plazo) == [alerta]
    assert len(slack.publicaciones) == 2
    url, texto = slack.publicaciones[1]
    assert url == URGENTE
    assert texto.startswith("@channel Escalamiento. Alerta Crítica. Doc: DOC-CLIN-2026-8942.")
    assert "Sin acuse de Jefe de Urgencias en 15 min." in texto and "Para: Coordinador Médico de Turno." in texto


# --- Avisos Urgentes (RN-F3) ---------------------------------------------------------------------


def test_un_documento_urgente_avisa_una_vez_al_canal_general_sin_acuse_RN_F3_RN_Q3(client, llm_falso, notificador_falso):
    urgente = propuesta(**{"clasificacion.nivel_prioridad_propuesto": "Urgente", "extraccion.hallazgos_criticos_detectados": [],
                           "extraccion.diagnosticos": [{"texto": "Insuficiencia cardíaca descompensada", "cie10_sugerido": "I50.9", "cie11_sugerido": None}],
                           "extraccion.signos_vitales": {"FR": 20, "SpO2": 95, "FC": 98, "PAS": 118, "Temp": None, "nivel_conciencia": "alerta"}})
    d = enviar(client, llm_falso, "URG-1", "Fecha: 03/04/2026. Paciente: Carlos Mendes, 52 años. Falla cardíaca descompensada. Dr. Rojas, RM 45678.", urgente,
               canal="Guardia_Emergencias")
    assert d["estado"] == "ENRUTADO" and d["nivel_prioridad"] == "Urgente"
    assert notificador_falso.avisos == [("Profesional solicitante", "URG-1")]
    assert notificador_falso.enviados == []  # sin acuse ni cadena de guardia
    assert client.get("/alertas").json() == []
    historial = client.get("/documentos/URG-1").json()["resultado"]["historial_decisiones"]
    assert [h["decision"] for h in historial if h["regla"] == "RN-F3"][-1] == "aviso enviado"
    # confirmar entregas vuelve a persistir el resultado: no se avisa dos veces
    client.post("/documentos/URG-1/entregar", json={"destino": "Historia_Clinica_Electronica"})
    assert len(notificador_falso.avisos) == 1


def test_rutina_no_avisa_y_critico_no_usa_el_canal_general_RN_Q3(client, llm_falso, notificador_falso):
    enviar(client, llm_falso, "RUT-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    enviar(client, llm_falso, "CRI-1", "Paciente: Carlos Mendes, 52 años. Fecha: 03/04/2026. TC: tromboembolismo pulmonar agudo. Dr. Rojas, RM 45678.",
           propuesta_caso_1(), canal="Guardia_Emergencias")
    assert notificador_falso.avisos == []
    assert [e[2] for e in notificador_falso.enviados] == ["CRI-1"]


def test_el_aviso_urgente_va_al_webhook_general_y_sin_canal_configurado_queda_registrado():
    slack = SlackSimulado()
    notificador(slack).avisar("Profesional solicitante", "Aviso Urgente. Doc: URG-9. Nivel: Urgente. Atención en 24 h.", "http://x/URG-9")
    assert slack.publicaciones == [(GENERAL, "Aviso Urgente. Doc: URG-9. Nivel: Urgente. Atención en 24 h. Para: Profesional solicitante. <http://x/URG-9|Abrir en MediFlow>")]
    with pytest.raises(CanalCaido):
        notificador(slack, Slack(avisos_urgentes=None)).avisar("Profesional solicitante", "Aviso Urgente. Doc: URG-9.", None)


def test_un_aviso_urgente_sin_canal_no_detiene_el_enrutamiento(repo, storage):
    cliente = ClienteFalso(respuestas=[fabricar(**{"clasificacion.nivel_prioridad_propuesto": "Urgente"}).model_dump(mode="json")])
    orq = Orquestador(repo, storage, ServicioExtraccion(cliente, max_intentos=1), notificador=NotificadorFalso(caidos={"Slack"}))
    doc = ingresar(repo, storage, request_caso_1(documento_id="URG-2", contenido_texto="Control. Fecha: 03/04/2026. Dr. Rojas, RM 45678."))
    resultado = orq.procesar(doc)
    assert resultado.clasificacion.nivel_prioridad is N.URGENTE and doc.estado == "ENRUTADO"
    assert any(d.regla == "RN-F3" and d.decision.startswith("aviso no enviado") for d in resultado.historial_decisiones)


# --- Selección por configuración --------------------------------------------------------------------


def test_sin_webhooks_se_usa_el_registro_y_con_uno_se_usa_slack(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "slack_webhook_url", "")
    monkeypatch.setattr(settings, "slack_webhook_url_urgente", "")
    get_notificador.cache_clear()
    assert isinstance(get_notificador(), NotificadorRegistro)
    monkeypatch.setattr(settings, "slack_webhook_url_urgente", URGENTE)
    get_notificador.cache_clear()
    elegido = get_notificador()
    assert isinstance(elegido, NotificadorSlack) and elegido.webhooks == {"urgente": URGENTE}
    get_notificador.cache_clear()
