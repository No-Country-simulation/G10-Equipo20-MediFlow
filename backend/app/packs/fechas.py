"""Fechas según el pack (RN-C8, RN-CO11). Una fecha imposible devuelve None y el
llamador decide si es clínicamente relevante y va a revisión humana."""
import re
from datetime import date

from app.packs.modelos import PackPais

_DIA_MES_ANIO = re.compile(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\s*$")
_ISO = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")


def parsear_fecha(texto: str | None, pack: PackPais) -> date | None:
    if not texto:
        return None
    if pack.formato.formato_fecha != "dd/mm/aaaa":
        raise NotImplementedError(f"Formato de fecha no soportado: {pack.formato.formato_fecha}")

    coincidencia = _DIA_MES_ANIO.match(texto)
    if coincidencia:
        dia, mes, anio = (int(g) for g in coincidencia.groups())
    else:
        coincidencia = _ISO.match(texto)
        if not coincidencia:
            return None
        anio, mes, dia = (int(g) for g in coincidencia.groups())
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def formatear_fecha(valor: date, pack: PackPais) -> str:
    patron = pack.formato.formato_fecha.replace("dd", "%d").replace("mm", "%m").replace("aaaa", "%Y")
    return valor.strftime(patron)
