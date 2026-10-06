"""Ciclo propio de las alertas críticas, fuera del grafo del documento (RN-F2, RN-P7, RN-Q2, RN-Q4).

La cadena de guardia y el orden de canales los configura la clínica (umbrales.yaml, sección notificaciones).
Emitir una alerta prueba los canales en orden; si ninguno funciona escala al siguiente rol y lo registra (RN-P7).
Un trabajo periódico escala las alertas sin acuse en el plazo y deja el escalamiento en el historial (RN-F2).
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from app.models.alerta import Alerta
from app.models.documento import Documento
from app.packs.modelos import Slack, Umbrales
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.resultado import DecisionRegistrada, NivelPrioridad as N, Notificacion

logger = logging.getLogger(__name__)


class CanalCaido(Exception):
    """El canal no pudo entregar la notificación (RN-P7)."""


class Notificador(Protocol):
    def enviar(self, canal: str, destinatario: str, mensaje: str, enlace: str | None) -> None:
        """Alerta crítica o su escalamiento: exige acuse (RN-F1, RN-F2)."""

    def avisar(self, destinatario: str, mensaje: str, enlace: str | None) -> None:
        """Aviso de nivel Urgente al solicitante: sin acuse ni escalamiento (RN-F3)."""


class NotificadorRegistro:
    """Sin Slack conectado: la alerta vive en la bandeja de la aplicación y el envío queda en el log, solo con el
    ID del documento (RN-Q4). Nunca falla, así que nunca fuerza un canal alternativo."""

    def enviar(self, canal: str, destinatario: str, mensaje: str, enlace: str | None) -> None:
        logger.info("Alerta por %s a %s: %s", canal, destinatario, mensaje)

    def avisar(self, destinatario: str, mensaje: str, enlace: str | None) -> None:
        logger.info("Aviso a %s: %s", destinatario, mensaje)


class NotificadorFalso:
    """Para pruebas: canales caídos (para todos o para ciertos destinatarios) y registro de lo enviado."""

    def __init__(self, caidos: set[str] | None = None, caidos_para: set[str] | None = None):
        self.caidos = set(caidos or ())
        self.caidos_para = set(caidos_para or ())
        self.enviados: list[tuple[str, str, str]] = []
        self.mensajes: list[str] = []
        self.avisos: list[tuple[str, str]] = []

    def enviar(self, canal: str, destinatario: str, mensaje: str, enlace: str | None) -> None:
        if canal in self.caidos and (not self.caidos_para or destinatario in self.caidos_para):
            raise CanalCaido(f"{canal} no responde")
        self.enviados.append((canal, destinatario, _documento_de(mensaje)))
        self.mensajes.append(mensaje)

    def avisar(self, destinatario: str, mensaje: str, enlace: str | None) -> None:
        if "Slack" in self.caidos:
            raise CanalCaido("Slack no responde")
        self.avisos.append((destinatario, _documento_de(mensaje)))


def _documento_de(mensaje: str) -> str:
    coincidencia = re.search(r"Doc: ([^\s.]+)", mensaje)
    return coincidencia.group(1) if coincidencia else "?"


class NotificadorSlack:
    """Slack por webhooks entrantes: cada webhook publica en un canal fijo. La alerta va al rol de la cadena de
    guardia y el canal es el del rol (RN-Q2); con un solo canal, el mensaje nombra a quién va dirigido.

    Solo viaja lo que permite RN-Q4: ID del documento, nivel, destinatario y enlace. La dirección del webhook es un
    secreto y no se escribe en el log. Un error o una demora mayor al tope es un canal caído (RN-P7).
    """

    def __init__(self, webhooks: dict[str, str], config: Slack, *, timeout_s: float = 5.0, cliente: Any = None):
        self.webhooks = {nombre: url for nombre, url in webhooks.items() if url}
        self.config = config
        self.timeout_s = timeout_s
        self._cliente = cliente

    @property
    def configurado(self) -> bool:
        return bool(self.webhooks)

    def enviar(self, canal: str, destinatario: str, mensaje: str, enlace: str | None) -> None:
        if canal != "Slack":
            raise CanalCaido(f"{canal} no está configurado en esta instalación")
        nombre = self.config.por_rol.get(destinatario, self.config.criticos)
        mencion = f"{self.config.mencion_criticos} " if self.config.mencion_criticos else ""
        self._publicar(nombre, f"{mencion}{mensaje} Para: {destinatario}.{_enlace(enlace)}")

    def avisar(self, destinatario: str, mensaje: str, enlace: str | None) -> None:
        if not self.config.avisos_urgentes:
            raise CanalCaido("los avisos de nivel Urgente no tienen canal en esta instalación")
        self._publicar(self.config.avisos_urgentes, f"{mensaje} Para: {destinatario}.{_enlace(enlace)}")

    def _publicar(self, nombre: str, texto: str) -> None:
        url = self.webhooks.get(nombre)
        if not url:
            raise CanalCaido(f"el canal de Slack '{nombre}' no tiene webhook configurado")
        import httpx  # noqa: PLC0415 - se importa al usarse para no exigirlo donde no hay Slack

        try:
            respuesta = (self._cliente or httpx).post(url, json={"text": texto}, timeout=self.timeout_s)
        except httpx.HTTPError as error:
            raise CanalCaido(f"Slack ({nombre}) no respondió: {type(error).__name__}") from None
        if respuesta.status_code >= 300:
            raise CanalCaido(f"Slack ({nombre}) rechazó el mensaje: HTTP {respuesta.status_code}")


def _enlace(enlace: str | None) -> str:
    return f" <{enlace}|Abrir en MediFlow>" if enlace else ""


def _utc(momento: datetime) -> datetime:
    return momento if momento.tzinfo is not None else momento.replace(tzinfo=timezone.utc)


class ServicioAlertas:
    def __init__(self, repo: RepositorioDocumentos, umbrales: Umbrales, notificador: Notificador | None = None):
        self.repo = repo
        self.umbrales = umbrales
        self.notificador = notificador or NotificadorRegistro()

    @property
    def cadena(self) -> list[str]:
        return list(self.umbrales.notificaciones.cadena_guardia)

    @property
    def canales(self) -> list[str]:
        return list(self.umbrales.notificaciones.canales)

    # --- emisión (RN-F1, RN-P7) ------------------------------------------------------------------

    def emitir(self, doc: Documento, notificacion: Notificacion, ahora: datetime | None = None) -> Alerta:
        """Crea la alerta crítica intentando los canales en orden. Si ninguno llega al destinatario,
        escala al siguiente rol de la cadena y lo registra (RN-P7). Siempre deja la alerta pendiente de acuse."""
        ahora = _utc(ahora or datetime.now(timezone.utc))  # SQLite devuelve fechas sin zona
        cadena = self.cadena
        destinatario = notificacion.destinatario if notificacion.destinatario in cadena else cadena[0]
        eventos: list[dict[str, Any]] = []
        canal = self._enviar_por_algun_canal(destinatario, notificacion.mensaje, notificacion.enlace, notificacion.canal, eventos, ahora)
        while canal is None:
            indice = cadena.index(destinatario)
            if indice + 1 >= len(cadena):
                eventos.append({"tipo": "sin_canal", "fecha_hora": ahora.isoformat(), "destinatario": destinatario,
                                "motivo": "RN-P7: ningún canal funcionó y la cadena de guardia está agotada; la alerta sigue en la bandeja"})
                break
            siguiente = cadena[indice + 1]
            eventos.append({"tipo": "escalamiento", "fecha_hora": ahora.isoformat(), "de": destinatario, "a": siguiente,
                            "motivo": f"RN-P7: ningún canal funcionó para {destinatario}"})
            destinatario = siguiente
            canal = self._enviar_por_algun_canal(destinatario, notificacion.mensaje, notificacion.enlace, notificacion.canal, eventos, ahora)
        alerta = self.repo.crear_alerta(doc, nivel=N.CRITICO.value, canal=canal or notificacion.canal, destinatario=destinatario,
                                        mensaje=notificacion.mensaje, enlace=notificacion.enlace)
        alerta.escalamientos = eventos
        return alerta

    def _enviar_por_algun_canal(self, destinatario: str, mensaje: str, enlace: str | None, preferido: str,
                                eventos: list[dict[str, Any]], ahora: datetime) -> str | None:
        orden = [preferido] + [c for c in self.canales if c != preferido]
        for canal in orden:
            try:
                self.notificador.enviar(canal, destinatario, mensaje, enlace)
            except CanalCaido as error:
                logger.warning("Canal %s caído para %s: %s", canal, destinatario, error)
                continue
            if canal != preferido:
                eventos.append({"tipo": "canal_alternativo", "fecha_hora": ahora.isoformat(), "de": preferido, "a": canal,
                                "destinatario": destinatario, "motivo": f"RN-P7: {preferido} caído"})
            return canal
        return None

    # --- escalamiento periódico (RN-F2) -----------------------------------------------------------

    def escalar_vencidas(self, ahora: datetime | None = None) -> list[Alerta]:
        """Toda alerta pendiente que lleve el plazo sin acuse desde su último movimiento sube un nivel de la
        cadena. Queda en el historial de la alerta y del documento. Con la cadena agotada no se inventa un rol más."""
        ahora = _utc(ahora or datetime.now(timezone.utc))  # SQLite devuelve fechas sin zona
        plazo = timedelta(minutes=self.umbrales.tiempos.escalamiento_sin_acuse_min)
        cadena = self.cadena
        escaladas: list[Alerta] = []
        for alerta in self.repo.listar_alertas(estado_acuse="pendiente", limit=10_000):
            if alerta.destinatario not in cadena:
                continue
            indice = cadena.index(alerta.destinatario)
            if indice + 1 >= len(cadena):
                continue
            eventos = list(alerta.escalamientos or [])
            movimientos = [datetime.fromisoformat(e["fecha_hora"]) for e in eventos if e.get("tipo") == "escalamiento"]
            ultimo = max([_utc(alerta.emitida_en), *movimientos])
            if ahora - ultimo < plazo:
                continue
            siguiente = cadena[indice + 1]
            minutos = self.umbrales.tiempos.escalamiento_sin_acuse_min
            eventos.append({"tipo": "escalamiento", "fecha_hora": ahora.isoformat(), "de": alerta.destinatario, "a": siguiente,
                            "motivo": f"RN-F2: sin acuse en {minutos} min"})
            mensaje = f"Escalamiento. {alerta.mensaje} Sin acuse de {alerta.destinatario} en {minutos} min."
            canal = self._enviar_por_algun_canal(siguiente, mensaje, alerta.enlace, alerta.canal, eventos, ahora)
            if canal is None:
                eventos.append({"tipo": "sin_canal", "fecha_hora": ahora.isoformat(), "destinatario": siguiente,
                                "motivo": "RN-P7: ningún canal funcionó; la alerta sigue en la bandeja"})
            else:
                alerta.canal = canal
            alerta.destinatario = siguiente
            alerta.escalamientos = eventos
            self._registrar_en_documento(alerta.documento, siguiente, minutos)
            escaladas.append(alerta)
        self.repo.guardar()
        return escaladas

    @staticmethod
    def _registrar_en_documento(doc: Documento, destinatario: str, minutos: int) -> None:
        """RN-F2: el escalamiento queda en el historial de decisiones del documento (RN-G2)."""
        resultado = dict(doc.resultado_json or {})
        decision = DecisionRegistrada(regla="RN-F2", evidencia=f"alerta crítica sin acuse en {minutos} min", decision=f"escalada a {destinatario}")
        resultado["historial_decisiones"] = list(resultado.get("historial_decisiones") or []) + [decision.model_dump(mode="json")]
        doc.resultado_json = resultado
