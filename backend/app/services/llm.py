"""Nodo LLM: clasificación y extracción con salida estructurada.

- RN-M1, RN-M3: al LLM va solo el texto seudonimizado y el contexto mínimo del request.
- RN-M2: en la ruta de imagen el LLM lee el original (excepción declarada).
- RN-P3: una respuesta fuera de esquema es un fallo; no se corrige adivinando ni se reintenta.
- RN-P2: los errores transitorios se reintentan con espera creciente; agotados, es FalloLLM.
- RN-R5, RN-T3: cada resultado lleva modelo, versión del prompt y tokens.
- RN-M10: se usa la API de OpenAI, nunca la aplicación ChatGPT.
"""
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.schemas.propuesta import PropuestaLLM

DIRECTORIO_PROMPTS = Path(__file__).resolve().parents[2] / "config" / "prompts"


# --- Errores -----------------------------------------------------------------


class ErrorTransitorioLLM(Exception):
    """Límite de tasa, timeout, red o error 5xx: se reintenta (RN-P2)."""


class RespuestaFueraDeEsquema(Exception):
    """RN-P3: el LLM no respetó el esquema. No se reintenta ni se adivina."""


class FalloLLM(Exception):
    """RN-P2: reintentos agotados. El documento va a revisión humana con motivo fallo_tecnico."""


# --- Contratos ---------------------------------------------------------------


@dataclass
class Prompt:
    version: str
    texto: str


@lru_cache
def cargar_prompt(version: str | None = None) -> Prompt:
    version = version or get_settings().prompt_version
    ruta = DIRECTORIO_PROMPTS / f"{version}.md"
    return Prompt(version=version, texto=ruta.read_text(encoding="utf-8"))


@dataclass
class EntradaLLM:
    documento_id: str
    texto: str | None
    canal_origen: str
    pais: str
    cobertura: str | None = None
    imagen_base64: str | None = None
    mime: str | None = None


@dataclass
class LlamadaLLM:
    system: str
    texto_usuario: str
    esquema: dict[str, Any]
    imagen_base64: str | None = None
    mime: str | None = None


@dataclass
class RespuestaLLM:
    contenido: dict[str, Any]
    modelo: str
    tokens_entrada: int = 0
    tokens_salida: int = 0


class ClienteLLM(Protocol):
    def completar_estructurado(self, llamada: LlamadaLLM) -> RespuestaLLM: ...


@dataclass
class ResultadoLLM:
    propuesta: PropuestaLLM
    modelo: str
    version_prompt: str
    tokens_entrada: int
    tokens_salida: int
    intentos: int


# --- Esquema estricto para OpenAI ----------------------------------------------

_CLAVES_NO_SOPORTADAS = {
    "default", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "pattern", "format", "title", "examples",
}


def _endurecer(nodo: Any) -> Any:
    if isinstance(nodo, list):
        return [_endurecer(v) for v in nodo]
    if not isinstance(nodo, dict):
        return nodo
    limpio = {k: _endurecer(v) for k, v in nodo.items() if k not in _CLAVES_NO_SOPORTADAS}
    if limpio.get("type") == "object" or "properties" in limpio:
        limpio["additionalProperties"] = False
        limpio["required"] = list(limpio.get("properties", {}).keys())
    return limpio


def esquema_json_estricto(modelo: type[BaseModel]) -> dict[str, Any]:
    """Esquema JSON en modo estricto: todo requerido, sin campos extra (RN-P3)."""
    return {"name": modelo.__name__, "strict": True, "schema": _endurecer(modelo.model_json_schema())}


# --- Clientes ----------------------------------------------------------------------


class ClienteFalso:
    """Cliente de prueba (RN-U4). Cada elemento de `respuestas` es un dict o una excepción a lanzar."""

    def __init__(self, respuestas: list[Any], *, tokens: tuple[int, int] = (0, 0), modelo: str = "falso"):
        self.respuestas = list(respuestas)
        self.tokens = tokens
        self.modelo = modelo
        self.llamadas: list[LlamadaLLM] = []

    def completar_estructurado(self, llamada: LlamadaLLM) -> RespuestaLLM:
        self.llamadas.append(llamada)
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return RespuestaLLM(respuesta, self.modelo, *self.tokens)


class ClienteOpenAI:
    """Cliente real. El SDK se importa al construirlo para no exigirlo en la suite unitaria."""

    def __init__(self, api_key: str | None = None, modelo: str | None = None, timeout_s: float | None = None):
        import openai  # noqa: PLC0415

        settings = get_settings()
        self._openai = openai
        self._cliente = openai.OpenAI(api_key=api_key or settings.openai_api_key, timeout=timeout_s or settings.openai_timeout_s)
        self.modelo = modelo or settings.openai_model

    def completar_estructurado(self, llamada: LlamadaLLM) -> RespuestaLLM:
        contenido_usuario: list[dict[str, Any]] = [{"type": "text", "text": llamada.texto_usuario}]
        if llamada.imagen_base64:
            contenido_usuario.append(
                {"type": "image_url", "image_url": {"url": f"data:{llamada.mime or 'image/png'};base64,{llamada.imagen_base64}"}}
            )
        try:
            respuesta = self._cliente.chat.completions.create(
                model=self.modelo,
                temperature=0,
                messages=[
                    {"role": "system", "content": llamada.system},
                    {"role": "user", "content": contenido_usuario},
                ],
                response_format={"type": "json_schema", "json_schema": llamada.esquema},
            )
        except (self._openai.RateLimitError, self._openai.APITimeoutError, self._openai.APIConnectionError,
                self._openai.InternalServerError) as error:
            raise ErrorTransitorioLLM(str(error)) from error

        eleccion = respuesta.choices[0]
        if getattr(eleccion.message, "refusal", None) or not eleccion.message.content:
            raise RespuestaFueraDeEsquema("el modelo no devolvió contenido")
        try:
            contenido = json.loads(eleccion.message.content)
        except json.JSONDecodeError as error:
            raise RespuestaFueraDeEsquema("la respuesta no es JSON") from error
        uso = respuesta.usage
        return RespuestaLLM(
            contenido,
            respuesta.model,
            tokens_entrada=getattr(uso, "prompt_tokens", 0) or 0,
            tokens_salida=getattr(uso, "completion_tokens", 0) or 0,
        )


# --- Servicio ----------------------------------------------------------------------


def _mensaje_usuario(entrada: EntradaLLM) -> str:
    lineas = [
        "### METADATOS DEL REQUEST ###",
        f"documento_id: {entrada.documento_id}",
        f"canal_origen: {entrada.canal_origen}",
        f"pais_origen: {entrada.pais}",
        f"cobertura_paciente: {entrada.cobertura or 'no_informada'}",
        "",
    ]
    if entrada.texto is not None:
        lineas += ["### TEXTO CLÍNICO (seudonimizado; los tokens [TIPO_n] se copian tal cual) ###", entrada.texto]
    else:
        lineas += ["### DOCUMENTO ###", "El documento es la imagen adjunta. Léela completa antes de responder."]
    return "\n".join(lineas)


class ServicioExtraccion:
    def __init__(
        self,
        cliente: ClienteLLM,
        *,
        prompt: Prompt | None = None,
        max_intentos: int = 3,
        espera_base_s: float = 1.0,
        dormir: Callable[[float], None] = time.sleep,
    ):
        self.cliente = cliente
        self.prompt = prompt or cargar_prompt()
        self.max_intentos = max_intentos
        self.espera_base_s = espera_base_s
        self.dormir = dormir
        self._esquema = esquema_json_estricto(PropuestaLLM)

    def procesar(self, entrada: EntradaLLM) -> ResultadoLLM:
        llamada = LlamadaLLM(
            system=self.prompt.texto,
            texto_usuario=_mensaje_usuario(entrada),
            esquema=self._esquema,
            imagen_base64=entrada.imagen_base64,
            mime=entrada.mime,
        )
        ultimo_error: Exception | None = None
        for intento in range(1, self.max_intentos + 1):
            try:
                respuesta = self.cliente.completar_estructurado(llamada)
            except ErrorTransitorioLLM as error:
                ultimo_error = error
                if intento < self.max_intentos:
                    self.dormir(self.espera_base_s * 2 ** (intento - 1))
                continue
            try:
                propuesta = PropuestaLLM.model_validate(respuesta.contenido)
            except ValidationError as error:
                raise RespuestaFueraDeEsquema(str(error)) from error
            return ResultadoLLM(
                propuesta=propuesta,
                modelo=respuesta.modelo,
                version_prompt=self.prompt.version,
                tokens_entrada=respuesta.tokens_entrada,
                tokens_salida=respuesta.tokens_salida,
                intentos=intento,
            )
        raise FalloLLM(f"reintentos agotados ({self.max_intentos}): {ultimo_error}")
