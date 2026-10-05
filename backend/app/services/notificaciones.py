"""Entrega real de las notificaciones que el pipeline ya decide emitir (RN-F1, RN-F3, RN-Q4).

Antes de este módulo, `Notificacion` (canal="Slack"/"Correo") solo se guardaba como dato:
nadie llamaba de verdad a Slack ni mandaba el correo. Este módulo es la pieza que faltaba,
separada a propósito de `orquestador.py` -- el orquestador decide SI y A QUIÉN avisar
(las reglas de negocio); esto solo sabe CÓMO entregarlo.

Dos canales, dos mecanismos simples (sin SDKs pesados, reutilizando `httpx` que ya es
dependencia del proyecto y `smtplib` de la librería estándar):

  - Slack: un Incoming Webhook (una URL por workspace/canal). Más simple que OAuth
    completo -- alcanza para "la alerta crítica le llega a un canal fijo", que es
    exactamente lo que pide RN-F1. Se crea en https://api.slack.com/apps -> tu app ->
    "Incoming Webhooks" -> "Add New Webhook to Workspace".
  - Correo: SMTP estándar (sirve con Gmail con contraseña de aplicación, SendGrid,
    Amazon SES, el que tenga el equipo).

RN-P6 (un fallo no debe tumbar el pipeline): ninguna falla de red aquí se propaga hacia
`orquestador.py` -- quien llama (`_enviar_slack_seguro` / `_enviar_correo_seguro`) ya
envuelve esto en try/except y solo deja un registro en el log.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Notificador(Protocol):
    def enviar_slack(self, *, mensaje: str, enlace: str | None) -> None: ...
    def enviar_slack_urgente(self, *, mensaje: str, enlace: str | None) -> None: ...
    def enviar_correo(self, *, destinatario: str, mensaje: str, enlace: str | None) -> None: ...


class NotificadorNulo:
    """Valor por defecto cuando Slack/SMTP no están configurados: no hace nada, no falla.
    Así el pipeline funciona igual en desarrollo o en la suite de pruebas, sin red."""

    def enviar_slack(self, *, mensaje: str, enlace: str | None) -> None:
        logger.info("Slack no configurado (SLACK_WEBHOOK_URL vacío); alerta solo queda en la base: %s", mensaje)

    def enviar_slack_urgente(self, *, mensaje: str, enlace: str | None) -> None:
        logger.info("Slack no configurado; aviso Urgente solo queda en el resultado: %s", mensaje)

    def enviar_correo(self, *, destinatario: str, mensaje: str, enlace: str | None) -> None:
        logger.info("SMTP no configurado; aviso de correo a %s solo queda en el resultado: %s", destinatario, mensaje)


class NotificadorProduccion:
    def __init__(
        self,
        *,
        slack_webhook_url: str = "",
        slack_webhook_url_urgente: str = "",
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_usuario: str = "",
        smtp_clave: str = "",
        smtp_remitente: str = "",
        smtp_destino_urgente: str = "",
        timeout_s: float = 10.0,
    ):
        self.slack_webhook_url = slack_webhook_url
        self.slack_webhook_url_urgente = slack_webhook_url_urgente
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_usuario = smtp_usuario
        self.smtp_clave = smtp_clave
        self.smtp_remitente = smtp_remitente or smtp_usuario
        self.smtp_destino_urgente = smtp_destino_urgente
        self.timeout_s = timeout_s

    def enviar_slack(self, *, mensaje: str, enlace: str | None) -> None:
        if not self.slack_webhook_url:
            raise RuntimeError("SLACK_WEBHOOK_URL no configurada")
        texto = mensaje + (f"\n<{enlace}|Abrir en MediFlow>" if enlace else "")
        respuesta = httpx.post(self.slack_webhook_url, json={"text": texto}, timeout=self.timeout_s)
        respuesta.raise_for_status()

    def enviar_slack_urgente(self, *, mensaje: str, enlace: str | None) -> None:
        """Mismo mecanismo que `enviar_slack`, pero a un segundo canal (o al mismo,
        si no se configuró uno aparte): para equipos que todavía no tienen correo
        funcionando y prefieren mandar también los avisos Urgente a Slack (RN-F3)."""
        webhook = self.slack_webhook_url_urgente or self.slack_webhook_url
        if not webhook:
            raise RuntimeError("ni SLACK_WEBHOOK_URL_URGENTE ni SLACK_WEBHOOK_URL están configurados")
        texto = "🟠 " + mensaje + (f"\n<{enlace}|Abrir en MediFlow>" if enlace else "")
        respuesta = httpx.post(webhook, json={"text": texto}, timeout=self.timeout_s)
        respuesta.raise_for_status()

    def enviar_correo(self, *, destinatario: str, mensaje: str, enlace: str | None) -> None:
        if not self.smtp_host:
            raise RuntimeError("SMTP_HOST no configurado")
        # RN-F3: "destinatario" hoy es un rol ("Profesional solicitante"), no una dirección real
        # -- el modelo de datos todavía no guarda el correo de quien pidió el documento. Mientras
        # tanto, el aviso cae a una casilla de respaldo configurada por el equipo.
        destino = self.smtp_destino_urgente or destinatario
        if "@" not in destino:
            raise RuntimeError(f"no hay una dirección de correo válida para {destinatario!r} "
                              "(configura SMTP_DESTINO_URGENTE)")
        cuerpo = EmailMessage()
        cuerpo["Subject"] = "MediFlow · Aviso de prioridad Urgente"
        cuerpo["From"] = self.smtp_remitente
        cuerpo["To"] = destino
        texto = mensaje + (f"\n\nAbrir en MediFlow: {enlace}" if enlace else "")
        cuerpo.set_content(texto)
        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout_s) as servidor:
            servidor.starttls()
            if self.smtp_usuario:
                servidor.login(self.smtp_usuario, self.smtp_clave)
            servidor.send_message(cuerpo)


def notificador_desde_settings() -> Notificador:
    """RN-S1: la instalación decide con sus propias variables de entorno si Slack/correo
    están activos. Sin configurar ninguna, se usa `NotificadorNulo` -- el pipeline sigue
    funcionando, simplemente nadie recibe el aviso fuera de la base de datos."""
    s = get_settings()
    if not s.slack_webhook_url and not s.slack_webhook_url_urgente and not s.smtp_host:
        return NotificadorNulo()
    return NotificadorProduccion(
        slack_webhook_url=s.slack_webhook_url, slack_webhook_url_urgente=s.slack_webhook_url_urgente,
        smtp_host=s.smtp_host, smtp_port=s.smtp_port,
        smtp_usuario=s.smtp_usuario, smtp_clave=s.smtp_clave,
        smtp_remitente=s.smtp_remitente, smtp_destino_urgente=s.smtp_destino_urgente,
    )
