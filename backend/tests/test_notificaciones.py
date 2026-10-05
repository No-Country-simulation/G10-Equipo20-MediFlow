"""app/services/notificaciones.py: entrega real de Slack (webhook) y correo (SMTP),
y su conexión con Orquestador._emitir_alerta (RN-F1, RN-F3, RN-P6)."""
import smtplib

import httpx
import pytest

from app.core.config import get_settings
from app.services.notificaciones import (NotificadorNulo, NotificadorProduccion,
                                         notificador_desde_settings)


# --- NotificadorNulo / selección por settings -----------------------------------------


def test_sin_nada_configurado_devuelve_notificador_nulo(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
    monkeypatch.setenv("SMTP_HOST", "")
    get_settings.cache_clear()
    assert isinstance(notificador_desde_settings(), NotificadorNulo)
    get_settings.cache_clear()


def test_con_slack_configurado_devuelve_notificador_produccion(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/x/y/z")
    get_settings.cache_clear()
    assert isinstance(notificador_desde_settings(), NotificadorProduccion)
    get_settings.cache_clear()


def test_notificador_nulo_no_lanza_nada():
    n = NotificadorNulo()
    n.enviar_slack(mensaje="hola", enlace=None)
    n.enviar_correo(destinatario="x", mensaje="hola", enlace=None)


# --- NotificadorProduccion: Slack --------------------------------------------------------


def test_enviar_slack_postea_al_webhook(monkeypatch):
    llamadas = {}

    def _post_falso(url, json, timeout):
        llamadas["url"], llamadas["json"] = url, json
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", _post_falso)
    n = NotificadorProduccion(slack_webhook_url="https://hooks.slack.com/services/x")
    n.enviar_slack(mensaje="Alerta Crítica. Doc: DOC-1.", enlace="https://mediflow/DOC-1")
    assert llamadas["url"] == "https://hooks.slack.com/services/x"
    assert "DOC-1" in llamadas["json"]["text"]
    assert "https://mediflow/DOC-1" in llamadas["json"]["text"]


def test_enviar_slack_sin_webhook_lanza_runtimeerror():
    with pytest.raises(RuntimeError, match="SLACK_WEBHOOK_URL"):
        NotificadorProduccion().enviar_slack(mensaje="x", enlace=None)


def test_enviar_slack_urgente_usa_su_propio_webhook_si_esta_configurado(monkeypatch):
    llamadas = []
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: (llamadas.append((url, json)),
                                                                   httpx.Response(200, request=httpx.Request("POST", url)))[1])
    n = NotificadorProduccion(slack_webhook_url="https://hooks.slack.com/critico",
                              slack_webhook_url_urgente="https://hooks.slack.com/urgente")
    n.enviar_slack_urgente(mensaje="Angina inestable. Doc: DOC-9.", enlace=None)
    assert llamadas[0][0] == "https://hooks.slack.com/urgente"
    assert "DOC-9" in llamadas[0][1]["text"]


def test_enviar_slack_urgente_cae_al_webhook_principal_si_no_hay_uno_propio(monkeypatch):
    llamadas = []
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: (llamadas.append(url),
                                                                   httpx.Response(200, request=httpx.Request("POST", url)))[1])
    n = NotificadorProduccion(slack_webhook_url="https://hooks.slack.com/unico")
    n.enviar_slack_urgente(mensaje="x", enlace=None)
    assert llamadas[0] == "https://hooks.slack.com/unico"


def test_enviar_slack_urgente_sin_ningun_webhook_lanza_runtimeerror():
    with pytest.raises(RuntimeError, match="SLACK_WEBHOOK_URL"):
        NotificadorProduccion().enviar_slack_urgente(mensaje="x", enlace=None)


def test_enviar_slack_propaga_el_error_http(monkeypatch):
    def _post_falso(url, json, timeout):
        return httpx.Response(500, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", _post_falso)
    with pytest.raises(httpx.HTTPStatusError):
        NotificadorProduccion(slack_webhook_url="https://x").enviar_slack(mensaje="x", enlace=None)


# --- NotificadorProduccion: correo --------------------------------------------------------


class _SMTPFalso:
    instancias = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.mensajes_enviados = []
        self.logueado_con = None
        type(self).instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, usuario, clave):
        self.logueado_con = (usuario, clave)

    def send_message(self, msg):
        self.mensajes_enviados.append(msg)


@pytest.fixture(autouse=True)
def _limpiar_smtp_falso():
    _SMTPFalso.instancias = []
    yield


def test_enviar_correo_manda_el_mensaje_por_smtp(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _SMTPFalso)
    n = NotificadorProduccion(smtp_host="smtp.resend.com", smtp_port=587, smtp_usuario="a@b.com",
                              smtp_clave="clave", smtp_destino_urgente="urgencias@mediflow-ips.co")
    n.enviar_correo(destinatario="Profesional solicitante", mensaje="Aviso Urgente. Doc: DOC-2.",
                    enlace="https://mediflow/DOC-2")
    instancia = _SMTPFalso.instancias[0]
    assert instancia.logueado_con == ("a@b.com", "clave")
    enviado = instancia.mensajes_enviados[0]
    assert enviado["To"] == "urgencias@mediflow-ips.co"
    assert "DOC-2" in enviado.get_content()


def test_enviar_correo_sin_destino_valido_lanza_runtimeerror(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _SMTPFalso)
    n = NotificadorProduccion(smtp_host="smtp.resend.com")  # sin smtp_destino_urgente
    with pytest.raises(RuntimeError, match="correo válida"):
        n.enviar_correo(destinatario="Profesional solicitante", mensaje="x", enlace=None)


def test_enviar_correo_sin_host_lanza_runtimeerror():
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        NotificadorProduccion().enviar_correo(destinatario="x@y.com", mensaje="x", enlace=None)
