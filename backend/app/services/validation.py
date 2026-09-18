import warnings
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from app.services.errors import DocumentError

EXTENSIONS = {".pdf": "pdf", ".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png"}


def validate_filename(filename: str | None) -> tuple[str, str]:
    # Conservar solo el nombre, incluso si el cliente utiliza separadores Windows.
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not name or len(name) > 255 or any(ord(char) < 32 for char in name):
        raise DocumentError(422, "Nombre de archivo invalido (maximo 255 caracteres).")
    expected = EXTENSIONS.get(Path(name).suffix.lower())
    if expected is None:
        raise DocumentError(415, "Solo se admiten PDF, JPG, JPEG y PNG.")
    return name, expected


def validate_content(path: Path, expected: str, size: int) -> str:
    if size == 0:
        raise DocumentError(422, "El archivo esta vacio.")
    with path.open("rb") as source:
        header = source.read(8)
    detected = None
    if header.startswith(b"%PDF-"):
        detected = "pdf"
    elif header.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "png"
    elif header.startswith(b"\xff\xd8\xff"):
        detected = "jpeg"
    elif header.startswith((b"GIF87a", b"GIF89a", b"BM", b"II*\x00", b"MM\x00*", b"RIFF")):
        raise DocumentError(415, "El contenido corresponde a un formato no admitido.")

    if detected is not None and detected != expected:
        raise DocumentError(415, "La extension no coincide con el contenido del archivo.")
    if detected is None:
        raise DocumentError(422, "El archivo no contiene un documento valido.")

    if detected == "pdf":
        try:
            with path.open("rb") as source:
                reader = PdfReader(source, strict=True)
                if reader.is_encrypted:
                    raise DocumentError(422, "No se admiten PDF cifrados.")
                if len(reader.pages) == 0:
                    raise DocumentError(422, "El PDF debe contener al menos una pagina.")
                # Forzar la lectura de cada pagina sin extraer ni interpretar texto.
                for page in reader.pages:
                    _ = page.mediabox
                    contents = page.get_contents()
                    if contents is not None:
                        contents.get_data()
        except DocumentError:
            raise
        except Exception as exc:
            raise DocumentError(422, "El PDF esta corrupto o no es compatible.") from exc
    else:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    if image.format.lower() != detected:
                        raise DocumentError(415, "Formato de imagen incompatible.")
                    image.verify()
                # verify no decodifica los pixeles: load detecta imagenes truncadas.
                with Image.open(path) as image:
                    image.load()
        except DocumentError:
            raise
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
                Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
            raise DocumentError(422, "La imagen esta corrupta o excede los limites de seguridad.") from exc
    return detected
