"""Todo lo que toca un PDF con pymupdf corre en un proceso aparte (RN-O5, RN-P5).

Un PDF malformado puede colgar o tumbar al proceso que lo abre. Aquí el padre manda los bytes por la entrada
estándar a un proceso hijo con límite de tiempo y recibe un JSON; si el hijo muere o no responde a tiempo, la
API sigue viva y el documento se rechaza con un código explícito. El hijo nunca ve otra cosa que el PDF.

Como módulo: `ejecutar(operacion, datos, ...)`. Como programa: `python -m app.services.pdf_aislado '<json>'`
con el PDF por la entrada estándar; es lo que el padre lanza, no algo que se use a mano.
"""
import base64
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services.errores_archivo import ArchivoInvalido

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parents[2]
TIEMPO_MAXIMO_POR_DEFECTO_S = 30.0
MAX_BYTES_RENDER = 60_000_000  # PNG de las páginas escaneadas de un PDF, en total: más que esto no viaja al LLM
ESCALA_RENDER = 2.0
# Una página con al menos este texto embebido va por la ruta de texto aunque tenga imágenes (logos, sellos).
MIN_CARACTERES_TEXTO = 40
OPERACIONES = ("leer", "renderizar", "contar", "extraer")


# --- lado del padre ------------------------------------------------------------------------------


def ejecutar(operacion: str, datos: bytes, *, timeout_s: float = TIEMPO_MAXIMO_POR_DEFECTO_S, **parametros: Any) -> dict:
    """Corre la operación en un proceso hijo y devuelve su resultado. Un error del PDF llega como ArchivoInvalido."""
    if operacion not in OPERACIONES:
        raise ValueError(f"operación desconocida: {operacion}")
    orden = json.dumps({"operacion": operacion, **parametros})
    try:
        proceso = subprocess.run([sys.executable, "-m", "app.services.pdf_aislado", orden], input=datos, capture_output=True,
                                 timeout=timeout_s, cwd=RAIZ, check=False)
    except subprocess.TimeoutExpired as error:
        logger.warning("Lectura de PDF (%s) sin respuesta en %.0f s", operacion, timeout_s)  # RN-M4: nada del contenido
        raise ArchivoInvalido("pdf_tiempo_excedido") from error
    if proceso.returncode != 0:
        logger.warning("El proceso de PDF (%s) terminó con código %s", operacion, proceso.returncode)
        raise ArchivoInvalido("pdf_corrupto")
    try:
        respuesta = json.loads(proceso.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        logger.warning("El proceso de PDF (%s) devolvió una respuesta ilegible", operacion)
        raise ArchivoInvalido("pdf_corrupto") from error
    if "error" in respuesta:
        raise ArchivoInvalido(respuesta["error"])
    return respuesta


# --- lado del hijo: solo aquí se importa pymupdf ---------------------------------------------------


def _leer(documento, *, max_paginas: int, max_caracteres: int) -> dict:
    if documento.page_count > max_paginas:
        return {"error": "limite_paginas"}  # RN-O5: se rechaza, nunca se trunca
    paginas: list[dict] = []
    total_texto = 0
    total_render = 0
    for indice, pagina in enumerate(documento, start=1):
        texto = pagina.get_text("text", sort=True)
        if len(texto.strip()) >= MIN_CARACTERES_TEXTO:
            total_texto += len(texto)
            if total_texto > max_caracteres:
                return {"error": "limite_caracteres"}
            paginas.append({"numero": indice, "texto": texto.strip()})
        else:
            import pymupdf  # noqa: PLC0415 - ya importado por el hijo; aquí solo por la matriz

            png = pagina.get_pixmap(matrix=pymupdf.Matrix(ESCALA_RENDER, ESCALA_RENDER), alpha=False).tobytes("png")
            total_render += len(png)
            if total_render > MAX_BYTES_RENDER:
                return {"error": "limite_render"}
            paginas.append({"numero": indice, "png": base64.b64encode(png).decode("ascii")})
    return {"num_paginas": documento.page_count, "paginas": paginas}


def _renderizar(documento, *, numero: int) -> dict:
    import pymupdf  # noqa: PLC0415

    if numero < 1 or numero > documento.page_count:
        return {"error": "pagina_no_encontrada"}
    pagina = documento[numero - 1]
    escala = min(2.0, 1500 / max(pagina.rect.width, 1), 2000 / max(pagina.rect.height, 1))
    png = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False).tobytes("png")
    return {"png": base64.b64encode(png).decode("ascii")}


def _extraer(documento, *, paginas: list[int]) -> dict:
    import pymupdf  # noqa: PLC0415

    if any(n < 1 or n > documento.page_count for n in paginas):
        return {"error": "pagina_no_encontrada"}
    with pymupdf.open() as destino:
        for numero in paginas:
            destino.insert_pdf(documento, from_page=numero - 1, to_page=numero - 1)
        return {"pdf": base64.b64encode(destino.tobytes()).decode("ascii")}


def _atender(orden: dict, datos: bytes) -> dict:
    import pymupdf  # noqa: PLC0415

    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    try:
        documento = pymupdf.open(stream=datos, filetype="pdf")
    except Exception:  # noqa: BLE001
        return {"error": "pdf_corrupto"}
    with documento:
        if documento.is_encrypted:
            return {"error": "pdf_cifrado"}
        if documento.page_count == 0:
            return {"error": "pdf_sin_paginas"}
        operacion = orden.get("operacion")
        if operacion == "contar":
            return {"num_paginas": documento.page_count}
        if operacion == "leer":
            return _leer(documento, max_paginas=int(orden["max_paginas"]), max_caracteres=int(orden["max_caracteres"]))
        if operacion == "renderizar":
            return _renderizar(documento, numero=int(orden["numero"]))
        if operacion == "extraer":
            return _extraer(documento, paginas=[int(n) for n in orden["paginas"]])
        return {"error": "pdf_corrupto"}


def main(argv: list[str]) -> int:
    try:
        orden = json.loads(argv[1])
        respuesta = _atender(orden, sys.stdin.buffer.read())
    except Exception:  # noqa: BLE001 - cualquier cosa que pase aquí es un PDF que no se pudo leer
        respuesta = {"error": "pdf_corrupto"}
    sys.stdout.write(json.dumps(respuesta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
