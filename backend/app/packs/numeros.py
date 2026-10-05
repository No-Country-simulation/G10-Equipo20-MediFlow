"""Cantidades clínicas según los separadores del pack (RN-C7, RN-CO10).

Leer 0,5 mg como 5 mg es un error de 10 veces. Leer 2.500 UI como 2,5 UI es un
error de mil veces. Por eso todo lo que no se pueda leer con certeza sale como
ambiguo y va a revisión humana, nunca se adivina.
"""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from app.packs.modelos import PackPais

_TOKEN_NUMERICO = re.compile(r"\d[\d.,]*")
# Evidencia de convención: un separador seguido de 1 o 2 cifras (nunca 3, que es el caso ambiguo).
_EVIDENCIA_COMA = re.compile(r"\d+,\d{1,2}(?!\d)")
_EVIDENCIA_PUNTO = re.compile(r"\d+\.\d{1,2}(?!\d)")


class Convencion(StrEnum):
    COMA_DECIMAL = "coma_decimal"
    PUNTO_DECIMAL = "punto_decimal"
    MIXTA = "mixta"
    INDETERMINADA = "indeterminada"


@dataclass
class Cantidad:
    texto: str
    valor: Decimal | None
    ambigua: bool = False
    motivo: str | None = None


def detectar_convencion(texto_documento: str) -> Convencion:
    """Qué convención decimal usa el resto del documento (RN-CO10)."""
    usa_coma = _EVIDENCIA_COMA.search(texto_documento) is not None
    usa_punto = _EVIDENCIA_PUNTO.search(texto_documento) is not None
    if usa_coma and usa_punto:
        return Convencion.MIXTA
    if usa_coma:
        return Convencion.COMA_DECIMAL
    if usa_punto:
        return Convencion.PUNTO_DECIMAL
    return Convencion.INDETERMINADA


def convencion_del_pack(pack: PackPais) -> Convencion:
    return Convencion.COMA_DECIMAL if pack.formato.separador_decimal == "," else Convencion.PUNTO_DECIMAL


def _ambigua(texto: str) -> Cantidad:
    return Cantidad(texto=texto, valor=None, ambigua=True, motivo="dosis_ambigua")


def parsear_cantidad(texto: str, *, convencion: Convencion, pack: PackPais) -> Cantidad:
    """Lee una cantidad con los separadores del pack.

    Reglas RN-CO10:
    - Varios grupos de miles (1.234.567) o miles más decimal (1.250,75) nunca son ambiguos.
    - Un separador seguido de exactamente tres cifras (5.000, 2,500) solo se lee si el
      resto del documento confirma la convención del pack. Si el documento es mixto o no
      da evidencia, la cantidad es ambigua.
    - Un separador con una o dos cifras después (0,5; 2.5; 12,5) siempre es decimal.
    """
    coincidencia = _TOKEN_NUMERICO.search(texto or "")
    if coincidencia is None:
        return _ambigua(texto)
    token = coincidencia.group(0).rstrip(".,")

    miles = re.escape(pack.formato.separador_miles)
    decimal = re.escape(pack.formato.separador_decimal)
    confirmada = convencion == convencion_del_pack(pack)

    try:
        if re.fullmatch(r"\d+", token):
            return Cantidad(texto, Decimal(token))

        # 1.234.567 -> varios grupos de miles: inequívoco.
        if re.fullmatch(rf"\d{{1,3}}({miles}\d{{3}}){{2,}}", token):
            return Cantidad(texto, Decimal(token.replace(pack.formato.separador_miles, "")))

        # 1.250,75 -> miles y decimal a la manera del pack: inequívoco.
        if re.fullmatch(rf"\d{{1,3}}({miles}\d{{3}})+{decimal}\d+", token):
            limpio = token.replace(pack.formato.separador_miles, "").replace(pack.formato.separador_decimal, ".")
            return Cantidad(texto, Decimal(limpio))

        # 5.000 -> un grupo de miles: solo si el documento confirma la convención del pack.
        if re.fullmatch(rf"\d{{1,3}}{miles}\d{{3}}", token):
            if confirmada:
                return Cantidad(texto, Decimal(token.replace(pack.formato.separador_miles, "")))
            return _ambigua(texto)

        # 2,500 -> decimal con tres cifras: solo si el documento confirma la convención del pack.
        if re.fullmatch(rf"\d+{decimal}\d{{3}}", token):
            if confirmada:
                return Cantidad(texto, Decimal(token.replace(pack.formato.separador_decimal, ".")))
            return _ambigua(texto)

        # 0,5 / 12,5 -> decimal del pack con 1-2 cifras o 4 o más: inequívoco.
        if re.fullmatch(rf"\d+{decimal}\d+", token):
            return Cantidad(texto, Decimal(token.replace(pack.formato.separador_decimal, ".")))

        # 2.5 -> el separador de miles del pack con 1-2 cifras no puede ser miles: es decimal.
        if re.fullmatch(rf"\d+{miles}\d{{1,2}}", token):
            return Cantidad(texto, Decimal(token.replace(pack.formato.separador_miles, ".")))
    except InvalidOperation:
        return _ambigua(texto)

    return _ambigua(texto)
