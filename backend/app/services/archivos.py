"""Validación de archivos por contenido y lectura de PDF (RN-A1, RN-O5, RN-M1, RN-M2).

Se valida lo que el archivo ES (bytes mágicos, estructura) y no lo que dice su extensión. Las páginas de PDF
con texto embebido salen como texto (y pasan por la seudonimización); solo las páginas escaneadas se
renderizan a PNG para la ruta de imagen del LLM. Todo lo que abre un PDF con pymupdf corre en un proceso
aparte con límite de tiempo (pdf_aislado): un PDF malformado no tumba ni cuelga la API.
"""
import base64
import io
import warnings
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from app.services.errores_archivo import ArchivoInvalido
from app.services.pdf_aislado import TIEMPO_MAXIMO_POR_DEFECTO_S, ejecutar

EXTENSIONES = {".pdf": "pdf", ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg"}
MIME = {"pdf": "application/pdf", "png": "image/png", "jpeg": "image/jpeg", "txt": "text/plain; charset=utf-8"}
EXTENSION_SALIDA = {"pdf": "pdf", "png": "png", "jpeg": "jpg", "txt": "txt"}
MAX_PAGINAS_POR_DEFECTO = 20
MAX_CARACTERES_POR_DEFECTO = 50_000

__all__ = ["ArchivoInvalido"]


def _tiempo_maximo_s() -> float:
    """RN-P5: lo que se espera al proceso que lee el PDF. Viene de la configuración, con un valor por defecto sin ella."""
    try:
        from app.core.config import get_settings  # noqa: PLC0415 - evita import circular en arranque

        return float(get_settings().pdf_tiempo_maximo_s)
    except Exception:  # noqa: BLE001 - sin configuración cargable, el valor por defecto
        return TIEMPO_MAXIMO_POR_DEFECTO_S


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
    textos_por_pagina: dict[int, str] = field(default_factory=dict)  # RN-O4: para detectar títulos de sub-documentos


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
    """Texto embebido por página; solo las páginas sin texto útil (escaneos) se renderizan a PNG. Corre en un proceso aparte."""
    respuesta = ejecutar("leer", datos, timeout_s=_tiempo_maximo_s(), max_paginas=max_paginas, max_caracteres=max_caracteres)
    textos: list[str] = []
    paginas_texto: list[int] = []
    paginas_imagen: list[tuple[int, bytes]] = []
    textos_por_pagina: dict[int, str] = {}
    for pagina in respuesta["paginas"]:
        numero = int(pagina["numero"])
        if "texto" in pagina:
            textos.append(f"--- página {numero} ---\n{pagina['texto']}")
            paginas_texto.append(numero)
            textos_por_pagina[numero] = pagina["texto"]
        else:
            paginas_imagen.append((numero, base64.b64decode(pagina["png"])))
    return LecturaPDF(
        num_paginas=int(respuesta["num_paginas"]),
        texto="\n\n".join(textos),
        paginas_texto=paginas_texto,
        paginas_imagen=paginas_imagen,
        textos_por_pagina=textos_por_pagina,
    )


def extraer_paginas(datos: bytes, paginas: list[int]) -> bytes:
    """RN-O4: un PDF nuevo con solo esas páginas del original, en ese orden."""
    return base64.b64decode(ejecutar("extraer", datos, timeout_s=_tiempo_maximo_s(), paginas=list(paginas))["pdf"])


def renderizar_pagina(datos: bytes, numero: int) -> bytes:
    """PNG de una página del PDF original, para la vista previa del revisor."""
    return base64.b64decode(ejecutar("renderizar", datos, timeout_s=_tiempo_maximo_s(), numero=numero)["png"])


def contar_paginas(datos: bytes) -> int:
    return int(ejecutar("contar", datos, timeout_s=_tiempo_maximo_s())["num_paginas"])
