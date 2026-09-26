"""Validación de archivos por contenido y lectura de PDF (RN-A1, RN-O5, RN-M1, RN-M2).

Idea traída de la rama bryan-segovia: se valida lo que el archivo ES (bytes mágicos,
estructura) y no lo que dice su extensión. Las páginas de PDF con texto embebido salen
como texto (y pasan por la seudonimización); solo las páginas escaneadas se renderizan
a PNG para la ruta de imagen del LLM.
"""
import io
import warnings
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath

import pymupdf
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

EXTENSIONES = {".pdf": "pdf", ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg"}
MIME = {"pdf": "application/pdf", "png": "image/png", "jpeg": "image/jpeg", "txt": "text/plain; charset=utf-8"}
EXTENSION_SALIDA = {"pdf": "pdf", "png": "png", "jpeg": "jpg", "txt": "txt"}
MAX_PAGINAS_POR_DEFECTO = 20
MAX_CARACTERES_POR_DEFECTO = 50_000
ESCALA_RENDER = 2.0


class ArchivoInvalido(Exception):
    def __init__(self, codigo: str):
        super().__init__(codigo)
        self.codigo = codigo


@dataclass
class ArchivoValidado:
    nombre: str
    formato: str  # pdf | png | jpeg
    tamano: int

    @property
    def tipo_contenido(self) -> str:
        return "pdf" if self.formato == "pdf" else "imagen"

    @property
    def mime(self) -> str:
        return MIME[self.formato]

    @property
    def extension(self) -> str:
        return EXTENSION_SALIDA[self.formato]


@dataclass
class LecturaPDF:
    num_paginas: int
    texto: str
    paginas_texto: list[int] = field(default_factory=list)
    paginas_imagen: list[tuple[int, bytes]] = field(default_factory=list)  # (número de página, PNG)


def nombre_base(nombre: str | None) -> str:
    """Solo el nombre, aunque el cliente mande rutas Windows o Unix."""
    crudo = (nombre or "").strip()
    crudo = PureWindowsPath(crudo).name if "\\" in crudo else PurePosixPath(crudo).name
    return "".join(c for c in crudo if ord(c) >= 32)[:255]


def _formato_detectado(datos: bytes) -> str | None:
    if datos.startswith(b"%PDF-"):
        return "pdf"
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if datos.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    return None


def _validar_pdf(datos: bytes) -> None:
    try:
        lector = PdfReader(io.BytesIO(datos), strict=True)
        if lector.is_encrypted:
            raise ArchivoInvalido("pdf_cifrado")
        if len(lector.pages) == 0:
            raise ArchivoInvalido("pdf_sin_paginas")
        for pagina in lector.pages:
            _ = pagina.mediabox
            contenido = pagina.get_contents()
            if contenido is not None:
                contenido.get_data()
    except ArchivoInvalido:
        raise
    except Exception as error:  # noqa: BLE001 - pypdf lanza muchas excepciones distintas
        raise ArchivoInvalido("pdf_corrupto") from error


def _validar_imagen(datos: bytes, formato: str) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(datos)) as imagen:
                if (imagen.format or "").lower() != formato:
                    raise ArchivoInvalido("extension_no_coincide")
                imagen.verify()
            with Image.open(io.BytesIO(datos)) as imagen:
                imagen.load()  # verify no decodifica los píxeles; load detecta imágenes truncadas
    except ArchivoInvalido:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError) as error:
        raise ArchivoInvalido("imagen_corrupta") from error


def validar_archivo(nombre: str | None, datos: bytes) -> ArchivoValidado:
    """RN-A1: PDF, JPG o PNG reales. Cualquier otra cosa se rechaza con código explícito."""
    limpio = nombre_base(nombre)
    if not limpio:
        raise ArchivoInvalido("nombre_invalido")
    esperado = EXTENSIONES.get(PurePosixPath(limpio).suffix.lower())
    if esperado is None:
        raise ArchivoInvalido("formato_no_soportado")
    if not datos:
        raise ArchivoInvalido("archivo_vacio")
    detectado = _formato_detectado(datos)
    if detectado is None:
        raise ArchivoInvalido("contenido_no_reconocido")
    if detectado != esperado:
        raise ArchivoInvalido("extension_no_coincide")
    if detectado == "pdf":
        _validar_pdf(datos)
    else:
        _validar_imagen(datos, detectado)
    return ArchivoValidado(nombre=limpio, formato=detectado, tamano=len(datos))


def leer_pdf(datos: bytes, *, max_paginas: int = MAX_PAGINAS_POR_DEFECTO, max_caracteres: int = MAX_CARACTERES_POR_DEFECTO) -> LecturaPDF:
    """Texto embebido por página; las páginas sin texto o con imagen se renderizan a PNG."""
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    try:
        documento = pymupdf.open(stream=datos, filetype="pdf")
    except Exception as error:  # noqa: BLE001
        raise ArchivoInvalido("pdf_corrupto") from error
    with documento:
        if documento.is_encrypted:
            raise ArchivoInvalido("pdf_cifrado")
        if documento.page_count == 0:
            raise ArchivoInvalido("pdf_sin_paginas")
        if documento.page_count > max_paginas:
            raise ArchivoInvalido("limite_paginas")  # RN-O5: se rechaza, nunca se trunca
        textos: list[str] = []
        paginas_texto: list[int] = []
        paginas_imagen: list[tuple[int, bytes]] = []
        total = 0
        for indice, pagina in enumerate(documento, start=1):
            texto = pagina.get_text("text", sort=True)
            if texto.strip() and not pagina.get_image_info():
                total += len(texto)
                if total > max_caracteres:
                    raise ArchivoInvalido("limite_caracteres")
                textos.append(f"--- página {indice} ---\n{texto.strip()}")
                paginas_texto.append(indice)
            else:
                pixmap = pagina.get_pixmap(matrix=pymupdf.Matrix(ESCALA_RENDER, ESCALA_RENDER), alpha=False)
                paginas_imagen.append((indice, pixmap.tobytes("png")))
        return LecturaPDF(
            num_paginas=documento.page_count,
            texto="\n\n".join(textos),
            paginas_texto=paginas_texto,
            paginas_imagen=paginas_imagen,
        )


def renderizar_pagina(datos: bytes, numero: int) -> bytes:
    """PNG de una página del PDF original, para la vista previa del revisor."""
    pymupdf.TOOLS.mupdf_display_errors(False)
    try:
        documento = pymupdf.open(stream=datos, filetype="pdf")
    except Exception as error:  # noqa: BLE001
        raise ArchivoInvalido("pdf_corrupto") from error
    with documento:
        if numero < 1 or numero > documento.page_count:
            raise ArchivoInvalido("pagina_no_encontrada")
        pagina = documento[numero - 1]
        escala = min(2.0, 1500 / max(pagina.rect.width, 1), 2000 / max(pagina.rect.height, 1))
        return pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False).tobytes("png")


def contar_paginas(datos: bytes) -> int:
    with pymupdf.open(stream=datos, filetype="pdf") as documento:
        return documento.page_count
