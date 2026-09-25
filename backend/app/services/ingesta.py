"""Ingesta y validación sin LLM: RECIBIDO -> VALIDADO o RECHAZADO (sección 3.3).

Orden fijo:
1. Calcular el hash del contenido y resolver duplicados (RN-O1, RN-O2, RN-O3).
2. Persistir como RECIBIDO y guardar el original antes de tocarlo (RN-P1, RN-G3).
3. Validar formato, tamaño y campos obligatorios (RN-A1, RN-O5). Único punto de rechazo (RN-I5).
"""
import base64
import binascii
import hashlib
import logging
from dataclasses import dataclass

from app.models.documento import Documento
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.request import DocumentoRequest, TipoContenido
from app.schemas.resultado import EstadoDocumento as E
from app.services.ciclo_vida import prefijo_storage
from app.services.storage import CONTENT_TYPES, Storage

logger = logging.getLogger(__name__)

TAMANO_MAXIMO_BYTES_POR_DEFECTO = 10_000_000  # RN-O5
ACTOR_SISTEMA = "sistema"


@dataclass
class ContenidoRecibido:
    datos: bytes
    extension: str
    codigo_error: str | None = None


@dataclass
class ResultadoIngesta:
    documento: Documento
    duplicado_exacto: bool = False  # RN-O1
    codigo_error: str | None = None


def _decodificar(request: DocumentoRequest) -> ContenidoRecibido:
    if request.tipo_contenido is TipoContenido.TEXTO:
        return ContenidoRecibido((request.contenido_texto or "").encode("utf-8"), "txt")
    crudo = request.archivo_base64 or ""
    extension = request.tipo_contenido.value if request.tipo_contenido is TipoContenido.PDF else "img"
    if request.nombre_archivo and "." in request.nombre_archivo:
        extension = request.nombre_archivo.rsplit(".", 1)[-1].lower()
    try:
        return ContenidoRecibido(base64.b64decode(crudo, validate=True), extension)
    except (binascii.Error, ValueError):
        # Se conserva lo recibido tal cual para no perder el documento (RN-P1, RN-M9).
        return ContenidoRecibido(crudo.encode("utf-8"), extension, codigo_error="archivo_invalido")


class ServicioIngesta:
    def __init__(
        self,
        repositorio: RepositorioDocumentos,
        storage: Storage,
        *,
        tamano_maximo_bytes: int = TAMANO_MAXIMO_BYTES_POR_DEFECTO,
    ):
        self.repositorio = repositorio
        self.storage = storage
        self.tamano_maximo_bytes = tamano_maximo_bytes

    def recibir(self, request: DocumentoRequest) -> ResultadoIngesta:
        contenido = _decodificar(request)
        hash_contenido = hashlib.sha256(contenido.datos).hexdigest()

        previo = self.repositorio.ultima_version(request.documento_id)
        if previo is not None and previo.hash_contenido == hash_contenido:
            # RN-O1: mismo documento_id y mismo contenido -> resultado previo, sin reprocesar ni alertar.
            return ResultadoIngesta(previo, duplicado_exacto=True, codigo_error=previo.codigo_error)

        version = previo.version + 1 if previo is not None else 1  # RN-O2
        otro = self.repositorio.por_hash(hash_contenido, excluir_documento_id=request.documento_id)

        documento = self.repositorio.crear_recibido(
            actor=ACTOR_SISTEMA,
            motivo="documento recibido",
            documento_id=request.documento_id,
            version=version,
            hash_contenido=hash_contenido,
            canal_origen=request.canal_origen.value,
            pais_origen=request.pais_origen,
            tipo_contenido=request.tipo_contenido.value,
            nombre_archivo=request.nombre_archivo,
            cobertura_paciente=request.cobertura_paciente.value if request.cobertura_paciente else None,
            tamano_bytes=len(contenido.datos),
            posible_duplicado_de=otro.documento_id if otro is not None else None,  # RN-O3
        )
        self._respaldar(documento, contenido, E.RECIBIDO)

        codigo_error = self._validar(contenido)
        if codigo_error is None:
            self.repositorio.transicionar(
                documento, E.VALIDADO, actor=ACTOR_SISTEMA, motivo="formato, tamaño, id y duplicados verificados"
            )
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

    def _respaldar(self, documento: Documento, contenido: ContenidoRecibido, estado: E) -> None:
        """RN-P1: el original se guarda antes de procesar. RN-G3: un fallo no invalida el triaje."""
        sufijo = f"_v{documento.version}" if documento.version > 1 else ""
        ruta = f"{prefijo_storage(estado, documento.pais_origen)}/{documento.documento_id}{sufijo}.{contenido.extension}"
        try:
            self.storage.guardar(ruta, contenido.datos, CONTENT_TYPES.get(contenido.extension, "application/octet-stream"))
        except Exception as error:  # noqa: BLE001 - cualquier fallo de respaldo se registra y se reintenta después
            logger.warning("Fallo de respaldo para %s: %s", documento.documento_id, error)  # RN-M4: solo el ID
            documento.status_backup = "error"
            return
        documento.status_backup = "ok"
        documento.ruta_storage = ruta
