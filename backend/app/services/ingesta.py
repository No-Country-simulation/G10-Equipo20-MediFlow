"""Ingesta y validación sin LLM: RECIBIDO -> VALIDADO o RECHAZADO (sección 3.3).

Orden fijo:
1. Calcular el hash del contenido y resolver duplicados (RN-O1, RN-O2, RN-O3).
2. Persistir como RECIBIDO y guardar el original antes de tocarlo (RN-P1, RN-G3).
3. Validar formato por contenido, tamaño y campos obligatorios (RN-A1, RN-O5). Único punto de rechazo (RN-I5).
4. Preparar el contenido para el LLM: texto seudonimizado (RN-M1) y páginas escaneadas como PNG (RN-M2).
"""
import base64
import binascii
import hashlib
import logging
from dataclasses import dataclass, field

from app.models.documento import Documento
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.request import DocumentoRequest, TipoContenido
from app.schemas.resultado import EstadoDocumento as E
from app.services.archivos import MIME, ArchivoInvalido, LecturaPDF, leer_pdf, validar_archivo
from app.services.ciclo_vida import prefijo_storage
from app.services.seudonimizacion import Seudonimizador
from app.services.storage import Storage

logger = logging.getLogger(__name__)

TAMANO_MAXIMO_BYTES_POR_DEFECTO = 10_000_000  # RN-O5
ACTOR_SISTEMA = "sistema"


@dataclass
class ContenidoRecibido:
    datos: bytes
    extension: str
    formato: str  # txt | pdf | png | jpeg
    tipo_contenido: str  # texto | pdf | imagen
    nombre_archivo: str | None = None
    codigo_error: str | None = None
    texto: str | None = None  # texto plano (ruta de texto)
    lectura: LecturaPDF | None = None
    nombres_conocidos: list[str] = field(default_factory=list)


@dataclass
class ResultadoIngesta:
    documento: Documento
    duplicado_exacto: bool = False  # RN-O1
    codigo_error: str | None = None


@dataclass
class DatosRequest:
    documento_id: str
    canal_origen: str
    pais_origen: str = "CO"
    cobertura_paciente: str | None = None
    metadatos: dict = field(default_factory=dict)

    @property
    def nombres_conocidos(self) -> list[str]:
        return [v for k, v in self.metadatos.items() if "nombre" in k.lower() and isinstance(v, str)]


def _desde_request(request: DocumentoRequest) -> DatosRequest:
    return DatosRequest(
        documento_id=request.documento_id,
        canal_origen=request.canal_origen.value,
        pais_origen=request.pais_origen,
        cobertura_paciente=request.cobertura_paciente.value if request.cobertura_paciente else None,
        metadatos=request.metadatos,
    )


class ServicioIngesta:
    def __init__(
        self,
        repositorio: RepositorioDocumentos,
        storage: Storage,
        *,
        tamano_maximo_bytes: int = TAMANO_MAXIMO_BYTES_POR_DEFECTO,
        max_paginas_pdf: int = 20,
    ):
        self.repositorio = repositorio
        self.storage = storage
        self.tamano_maximo_bytes = tamano_maximo_bytes
        self.max_paginas_pdf = max_paginas_pdf
        self.seudonimizador = Seudonimizador()

    # --- entradas ------------------------------------------------------------------

    def recibir(self, request: DocumentoRequest) -> ResultadoIngesta:
        """Request JSON: texto plano o archivo en base64."""
        datos = _desde_request(request)
        if request.tipo_contenido is TipoContenido.TEXTO:
            texto = request.contenido_texto or ""
            contenido = ContenidoRecibido(texto.encode("utf-8"), "txt", "txt", "texto", texto=texto)
        else:
            crudo = request.archivo_base64 or ""
            try:
                binario = base64.b64decode(crudo, validate=True)
            except (binascii.Error, ValueError):
                # Se conserva lo recibido tal cual para no perder el documento (RN-P1, RN-M9).
                contenido = ContenidoRecibido(crudo.encode("utf-8"), "bin", "desconocido", request.tipo_contenido.value,
                                              nombre_archivo=request.nombre_archivo, codigo_error="archivo_invalido")
            else:
                nombre = request.nombre_archivo or f"{request.documento_id}.{'pdf' if request.tipo_contenido is TipoContenido.PDF else 'png'}"
                contenido = self._analizar_archivo(nombre, binario)
        return self._ingresar(datos, contenido)

    def recibir_archivo(self, nombre: str | None, binario: bytes, *, documento_id: str, canal_origen: str,
                        pais_origen: str = "CO", cobertura_paciente: str | None = None, metadatos: dict | None = None) -> ResultadoIngesta:
        """Carga multipart (PDF, PNG, JPG) validada por contenido."""
        datos = DatosRequest(documento_id=documento_id, canal_origen=canal_origen, pais_origen=pais_origen,
                             cobertura_paciente=cobertura_paciente, metadatos=metadatos or {})
        return self._ingresar(datos, self._analizar_archivo(nombre, binario))

    # --- núcleo ------------------------------------------------------------------------

    def _analizar_archivo(self, nombre: str | None, binario: bytes) -> ContenidoRecibido:
        try:
            archivo = validar_archivo(nombre, binario)
        except ArchivoInvalido as error:
            extension = (nombre or "").rsplit(".", 1)[-1].lower() if nombre and "." in nombre else "bin"
            return ContenidoRecibido(binario, extension[:8] or "bin", "desconocido", "pdf" if extension == "pdf" else "imagen",
                                     nombre_archivo=nombre, codigo_error=error.codigo)
        contenido = ContenidoRecibido(binario, archivo.extension, archivo.formato, archivo.tipo_contenido, nombre_archivo=archivo.nombre)
        if archivo.formato == "pdf":
            try:
                contenido.lectura = leer_pdf(binario, max_paginas=self.max_paginas_pdf)
                contenido.texto = contenido.lectura.texto
            except ArchivoInvalido as error:
                contenido.codigo_error = error.codigo
        return contenido

    def _ingresar(self, datos: DatosRequest, contenido: ContenidoRecibido) -> ResultadoIngesta:
        hash_contenido = hashlib.sha256(contenido.datos).hexdigest()

        previo = self.repositorio.ultima_version(datos.documento_id)
        if previo is not None and previo.hash_contenido == hash_contenido:
            # RN-O1: mismo documento_id y mismo contenido -> resultado previo, sin reprocesar ni alertar.
            return ResultadoIngesta(previo, duplicado_exacto=True, codigo_error=previo.codigo_error)

        version = previo.version + 1 if previo is not None else 1  # RN-O2
        otro = self.repositorio.por_hash(hash_contenido, excluir_documento_id=datos.documento_id)

        documento = self.repositorio.crear_recibido(
            actor=ACTOR_SISTEMA,
            motivo="documento recibido",
            documento_id=datos.documento_id,
            version=version,
            hash_contenido=hash_contenido,
            canal_origen=datos.canal_origen,
            pais_origen=datos.pais_origen,
            tipo_contenido=contenido.tipo_contenido,
            formato=contenido.formato,
            nombre_archivo=contenido.nombre_archivo,
            cobertura_paciente=datos.cobertura_paciente,
            tamano_bytes=len(contenido.datos),
            num_paginas=contenido.lectura.num_paginas if contenido.lectura else 1,
            posible_duplicado_de=otro.documento_id if otro is not None else None,  # RN-O3
        )
        self._respaldar(documento, contenido, E.RECIBIDO)

        codigo_error = self._validar(contenido)
        if codigo_error is None:
            self.repositorio.transicionar(
                documento, E.VALIDADO, actor=ACTOR_SISTEMA, motivo="formato, tamaño, id y duplicados verificados"
            )
            self._preparar_contenido(documento, contenido, datos.nombres_conocidos)
        else:
            documento.codigo_error = codigo_error
            self.repositorio.transicionar(documento, E.RECHAZADO, actor=ACTOR_SISTEMA, motivo=codigo_error)
            self._respaldar(documento, contenido, E.RECHAZADO)  # RN-M9

        self.repositorio.guardar()
        return ResultadoIngesta(documento, codigo_error=codigo_error)

    def _validar(self, contenido: ContenidoRecibido) -> str | None:
        if contenido.codigo_error:
            return contenido.codigo_error
        if len(contenido.datos) > self.tamano_maximo_bytes:
            return "tamano_excedido"  # RN-O5: se rechaza, nunca se trunca
        return None

    def _preparar_contenido(self, documento: Documento, contenido: ContenidoRecibido, nombres_conocidos: list[str]) -> None:
        """RN-M1: el texto se tokeniza aquí. RN-M2: las páginas escaneadas se guardan como PNG para el LLM."""
        resultado = self.seudonimizador.seudonimizar(contenido.texto or "", nombres_conocidos=nombres_conocidos)
        documento.texto_seudonimizado = resultado.texto
        documento.mapa_reidentificacion = resultado.mapa

        paginas: list[dict] = []
        if contenido.tipo_contenido == "texto":
            paginas.append({"pagina": 1, "tipo": "texto"})
        elif contenido.tipo_contenido == "imagen":
            paginas.append({"pagina": 1, "tipo": "imagen", "ruta": documento.ruta_storage})
        elif contenido.lectura is not None:
            for numero in contenido.lectura.paginas_texto:
                paginas.append({"pagina": numero, "tipo": "texto"})
            for numero, png in contenido.lectura.paginas_imagen:
                ruta = f"{prefijo_storage(E.RECIBIDO, documento.pais_origen)}/{documento.documento_id}{self._sufijo(documento)}_pag{numero}.png"
                try:
                    self.storage.guardar(ruta, png, "image/png")
                except Exception as error:  # noqa: BLE001
                    logger.warning("Fallo al guardar la página %s de %s: %s", numero, documento.documento_id, error)
                    documento.status_backup = "error"
                    ruta = None
                paginas.append({"pagina": numero, "tipo": "imagen", "ruta": ruta})
            paginas.sort(key=lambda p: p["pagina"])
        documento.paginas_json = paginas

    @staticmethod
    def _sufijo(documento: Documento) -> str:
        return f"_v{documento.version}" if documento.version > 1 else ""

    def _respaldar(self, documento: Documento, contenido: ContenidoRecibido, estado: E) -> None:
        """RN-P1: el original se guarda antes de procesar. RN-G3: un fallo no invalida el triaje."""
        ruta = f"{prefijo_storage(estado, documento.pais_origen)}/{documento.documento_id}{self._sufijo(documento)}.{contenido.extension}"
        try:
            self.storage.guardar(ruta, contenido.datos, MIME.get(contenido.formato, "application/octet-stream"))
        except Exception as error:  # noqa: BLE001 - cualquier fallo de respaldo se registra y se reintenta después
            logger.warning("Fallo de respaldo para %s: %s", documento.documento_id, error)  # RN-M4: solo el ID
            documento.status_backup = "error"
            return
        documento.status_backup = "ok"
        documento.ruta_storage = ruta
