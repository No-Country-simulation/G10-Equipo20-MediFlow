"""RN-O4: un PDF compuesto se divide en sub-documentos.

Hay dos formas de saber dónde cortar. La explícita: quien envía declara las páginas de cada documento
("1-2,3,4-6"). La automática: una página de texto que empieza con el título de un tipo de documento del
vocabulario del pack (FÓRMULA MÉDICA, EPICRISIS, ORDEN DE SERVICIOS…) distinto del que venía abre un
sub-documento nuevo. Las páginas escaneadas y las que no traen título siguen con el documento en curso.
"""
import re
import unicodedata

from app.schemas.resultado import TipoDocumento
from app.services.archivos import ArchivoInvalido

LINEAS_DE_TITULO = 2  # el título de un documento está en sus primeras líneas, no en cualquier parte de la página
TIPOS_DOCUMENTO = {t.value for t in TipoDocumento}


def _normalizar(texto: str) -> str:
    sin_acentos = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()


def titulos_por_tipo(vocabulario: dict[str, list[str]]) -> dict[str, list[str]]:
    """Del vocabulario del pack, solo las entradas que son tipos de documento (RN-B1)."""
    return {tipo: [_normalizar(t) for t in terminos] for tipo, terminos in vocabulario.items() if tipo in TIPOS_DOCUMENTO}


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def tipo_por_titulo(texto: str, titulos: dict[str, list[str]]) -> str | None:
    """El tipo de documento cuyo título encabeza la página, o None. Un título empieza la línea o va en
    mayúsculas tras el membrete (MediFlow IPS   EPICRISIS); la misma palabra dentro de una frase no lo es."""
    lineas = [l for l in texto.splitlines() if l.strip()][:LINEAS_DE_TITULO]
    for linea in lineas:
        normalizada = _normalizar(linea)
        en_mayusculas = re.sub(r"\s+", " ", _sin_acentos(linea)).strip()
        for tipo, terminos in titulos.items():
            for termino in sorted(terminos, key=len, reverse=True):
                patron = re.escape(termino)
                if re.match(rf"^\W*{patron}\b", normalizada) or re.search(rf"\b{patron.upper()}\b", en_mayusculas):
                    return tipo
    return None


def segmentar_por_titulos(num_paginas: int, textos_por_pagina: dict[int, str], titulos: dict[str, list[str]]) -> list[list[int]]:
    """Rangos de páginas de cada sub-documento. Un solo rango significa que el PDF no es compuesto."""
    segmentos: list[list[int]] = []
    tipo_actual: str | None = None
    for numero in range(1, num_paginas + 1):
        tipo = tipo_por_titulo(textos_por_pagina.get(numero, ""), titulos) if numero in textos_por_pagina else None
        if segmentos and (tipo is None or tipo == tipo_actual):
            segmentos[-1].append(numero)
            continue
        segmentos.append([numero])
        tipo_actual = tipo
    return segmentos


def parsear_rangos(texto: str, num_paginas: int) -> list[list[int]]:
    """"1-2,3,4-6" -> [[1, 2], [3], [4, 5, 6]]. Debe cubrir todas las páginas, en orden y sin solapar, en dos o más partes."""
    segmentos: list[list[int]] = []
    esperada = 1
    for parte in texto.split(","):
        parte = parte.strip()
        m = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", parte)
        if not m:
            raise ArchivoInvalido("division_invalida")
        desde, hasta = int(m.group(1)), int(m.group(2) or m.group(1))
        if desde != esperada or hasta < desde or hasta > num_paginas:
            raise ArchivoInvalido("division_invalida")
        segmentos.append(list(range(desde, hasta + 1)))
        esperada = hasta + 1
    if esperada != num_paginas + 1 or len(segmentos) < 2:
        raise ArchivoInvalido("division_invalida")
    return segmentos


def describir(segmentos: list[list[int]]) -> str:
    return ", ".join(f"{s[0]}-{s[-1]}" if len(s) > 1 else str(s[0]) for s in segmentos)
