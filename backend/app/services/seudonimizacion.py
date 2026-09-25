"""Seudonimización de la ruta de texto (RN-M1, RN-M3, RN-M4).

Antes de enviar texto a OpenAI, los nombres, identificadores, fechas exactas,
direcciones, teléfonos y correos se reemplazan por tokens de la forma [TIPO_n].
El mapa token -> original se guarda en la instalación y nunca sale de ella.

Se conservan a propósito: edades (RN-A4 exige nombre + edad), signos vitales,
dosis, códigos y el número de registro profesional. Todo es determinístico:
no se usa el LLM para detectar datos personales.
"""
import re
from dataclasses import dataclass, field
from typing import Any

# Palabra de nombre propio: Capitalizada o EN MAYÚSCULAS. Conectores habituales en nombres.
_W = r"(?:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+|[A-ZÁÉÍÓÚÑ]{2,})"
_C = r"(?:de|del|la|las|los|y|De|Del)"
_NOMBRE = rf"{_W}(?:\s+(?:{_C}\s+)?{_W}){{1,4}}"

_CUE_PACIENTE = (
    r"(?:nombre(?:\s+y\s+apellidos?|\s+del\s+paciente|\s+completo)?|paciente|sr\.?|sra\.?|se[ñn]or|se[ñn]ora|don|do[ñn]a)"
)
_CUE_PROFESIONAL = (
    r"(?:dr\.?|dra\.?|doctora?|m[eé]dico(?:\s+tratante)?|profesional|prescriptor|firma|atendido\s+por|especialista)"
)
_CUE_ID = (
    r"(?:C\.?C\.?|T\.?I\.?|R\.?C\.?|C\.?E\.?|P\.?A\.?|P\.?T\.?|NUIP|c[eé]dula(?:\s+de\s+(?:ciudadan[ií]a|extranjer[ií]a))?"
    r"|tarjeta\s+de\s+identidad|registro\s+civil|documento(?:\s+de\s+identidad)?|identificaci[oó]n|identificado\s+con)"
)
_NUM_ID = r"\d[\d.]{4,13}\d"
_SEP_NO = r"(?:\s*(?:n[°º.]?|no\.?|nro\.?|#)\s*)?[:\-]?\s*"

_MESES = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"

_PATRONES: list[tuple[str, re.Pattern[str], int]] = [
    # (tipo de token, patrón, grupo que se reemplaza)
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), 0),
    (
        "DIRECCION",
        re.compile(
            r"\b(?:calle|cll|cl|carrera|cra|cr|kr|avenida|av|avda|diagonal|dg|transversal|tv|tr)\.?\s+\d+[a-z]?"
            r"(?:\s*bis)?\s*(?:#|n[°º.]?|no\.?)\s*\d+[a-z]?\s*-\s*\d+",
            re.IGNORECASE,
        ),
        0,
    ),
    ("NIT", re.compile(r"\bNIT\.?" + _SEP_NO + r"(" + _NUM_ID + r"\s*-\s*\d)", re.IGNORECASE), 1),
    ("ID", re.compile(r"\b" + _CUE_ID + _SEP_NO + r"(" + _NUM_ID + r")(?!\d)", re.IGNORECASE), 1),
    (
        "TEL",
        re.compile(r"(?:\+57\s?)?(?:\(?60\d\)?[\s-]?\d{3}[\s-]?\d{4}|3\d{2}[\s-]?\d{3}[\s-]?\d{4})(?!\d)"),
        0,
    ),
    ("FECHA", re.compile(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}\b|\b\d{4}-\d{2}-\d{2}\b"), 0),
    ("FECHA", re.compile(rf"\b\d{{1,2}}\s+de\s+(?:{_MESES})(?:\s+de(?:l)?\s+\d{{4}})?\b", re.IGNORECASE), 0),
    # Número largo sin etiqueta: 8 a 11 dígitos seguidos (los valores de laboratorio no llegan a 8 cifras).
    ("ID", re.compile(r"(?<![\d.,])\d{8,11}(?!\d)"), 0),
    ("PROFESIONAL", re.compile(r"\b" + _CUE_PROFESIONAL + r"\s*[:\-]?\s*(" + _NOMBRE + r")", re.IGNORECASE), 1),
    ("PACIENTE", re.compile(r"\b" + _CUE_PACIENTE + r"\s*[:\-]?\s*(" + _NOMBRE + r")", re.IGNORECASE), 1),
]


@dataclass
class ResultadoSeudonimizacion:
    texto: str
    mapa: dict[str, str] = field(default_factory=dict)  # token -> original

    @property
    def entidades(self) -> int:
        return len(self.mapa)


class Seudonimizador:
    def seudonimizar(self, texto: str, *, nombres_conocidos: list[str] | None = None) -> ResultadoSeudonimizacion:
        if not texto:
            return ResultadoSeudonimizacion("")
        tokens_por_valor: dict[tuple[str, str], str] = {}
        contadores: dict[str, int] = {}
        mapa: dict[str, str] = {}

        def token_para(tipo: str, original: str) -> str:
            clave = (tipo, original)
            if clave not in tokens_por_valor:
                contadores[tipo] = contadores.get(tipo, 0) + 1
                token = f"[{tipo}_{contadores[tipo]}]"
                tokens_por_valor[clave] = token
                mapa[token] = original
            return tokens_por_valor[clave]

        resultado = texto
        # Nombres conocidos (por ejemplo, de los metadatos del request) van primero: no dependen de etiquetas.
        for nombre in sorted(filter(None, nombres_conocidos or []), key=len, reverse=True):
            nombre = nombre.strip()
            partes = [p for p in nombre.split() if len(p) >= 4]
            for fragmento in [nombre, *partes]:
                patron = re.compile(r"(?<!\[)\b" + re.escape(fragmento) + r"\b", re.IGNORECASE)
                resultado = patron.sub(lambda m, n=nombre: token_para("PACIENTE", m.group(0)), resultado)

        for tipo, patron, grupo in _PATRONES:

            def reemplazo(m: re.Match[str], tipo=tipo, grupo=grupo) -> str:
                original = m.group(grupo)
                token = token_para(tipo, original)
                if grupo == 0:
                    return token
                inicio, fin = m.span(grupo)
                return m.group(0)[: inicio - m.start()] + token + m.group(0)[fin - m.start() :]

            resultado = patron.sub(reemplazo, resultado)

        return ResultadoSeudonimizacion(resultado, mapa)


def reidentificar(texto: str, mapa: dict[str, str]) -> str:
    """Devuelve el texto original a partir del tokenizado. Solo se usa dentro de la instalación."""
    for token, original in sorted(mapa.items(), key=lambda par: len(par[0]), reverse=True):
        texto = texto.replace(token, original)
    return texto


def reidentificar_estructura(valor: Any, mapa: dict[str, str]) -> Any:
    """Aplica `reidentificar` a toda cadena dentro de un dict o lista (la salida del LLM). No muta la entrada."""
    if isinstance(valor, str):
        return reidentificar(valor, mapa)
    if isinstance(valor, dict):
        return {clave: reidentificar_estructura(v, mapa) for clave, v in valor.items()}
    if isinstance(valor, list):
        return [reidentificar_estructura(v, mapa) for v in valor]
    return valor
