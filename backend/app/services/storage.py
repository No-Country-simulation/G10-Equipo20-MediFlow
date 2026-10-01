"""Almacenamiento de originales y resultados (RN-G1, RN-P1).

En el MVP es un solo bucket con prefijo por país. `StorageLocal` sirve para
desarrollo y tests; `StorageOCI` usa OCI Object Storage (capa Always Free);
`StorageR2` usa el bucket de Cloudflare R2 que comparte el equipo.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ObjetoGuardado:
    ruta: str
    modificado: datetime
    tamano: int


class Storage(Protocol):
    def guardar(self, ruta: str, contenido: bytes, content_type: str = "application/octet-stream") -> None: ...

    def leer(self, ruta: str) -> bytes: ...

    def borrar(self, ruta: str) -> None: ...

    def listar(self, prefijo: str = "") -> list[ObjetoGuardado]: ...


class StorageLocal:
    def __init__(self, directorio_base: Path | str):
        self.base = Path(directorio_base).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _resolver(self, ruta: str) -> Path:
        destino = (self.base / ruta).resolve()
        if self.base not in destino.parents and destino != self.base:
            raise ValueError(f"Ruta fuera del bucket: {ruta}")
        return destino

    def guardar(self, ruta: str, contenido: bytes, content_type: str = "application/octet-stream") -> None:
        destino = self._resolver(ruta)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)

    def leer(self, ruta: str) -> bytes:
        return self._resolver(ruta).read_bytes()

    def borrar(self, ruta: str) -> None:
        self._resolver(ruta).unlink(missing_ok=True)

    def listar(self, prefijo: str = "") -> list[ObjetoGuardado]:
        raiz = self._resolver(prefijo) if prefijo else self.base
        archivos = [raiz] if raiz.is_file() else sorted(p for p in raiz.rglob("*") if p.is_file()) if raiz.is_dir() else []
        return [ObjetoGuardado(p.relative_to(self.base).as_posix(), datetime.fromtimestamp(p.stat().st_mtime, timezone.utc), p.stat().st_size)
                for p in archivos]


class StorageOCI:
    """OCI Object Storage. El SDK se importa al usarse para no exigirlo en tests (RN-U4)."""

    def __init__(self, namespace: str, bucket: str, region: str | None = None):
        import oci  # noqa: PLC0415

        config = oci.config.from_file()
        if region:
            config["region"] = region
        self._cliente = oci.object_storage.ObjectStorageClient(config)
        self.namespace = namespace
        self.bucket = bucket

    def guardar(self, ruta: str, contenido: bytes, content_type: str = "application/octet-stream") -> None:
        self._cliente.put_object(self.namespace, self.bucket, ruta, contenido, content_type=content_type)

    def leer(self, ruta: str) -> bytes:
        return self._cliente.get_object(self.namespace, self.bucket, ruta).data.content

    def borrar(self, ruta: str) -> None:
        self._cliente.delete_object(self.namespace, self.bucket, ruta)

    def listar(self, prefijo: str = "") -> list[ObjetoGuardado]:
        objetos: list[ObjetoGuardado] = []
        desde = None
        while True:
            pagina = self._cliente.list_objects(self.namespace, self.bucket, prefix=prefijo or None, start=desde, fields="name,timeCreated,size").data
            objetos += [ObjetoGuardado(o.name, o.time_created, o.size or 0) for o in pagina.objects]
            desde = pagina.next_start_with
            if not desde:
                return objetos


class StorageR2:
    """Cloudflare R2 por su API compatible con S3. El SDK se importa al usarse para no exigirlo en tests (RN-U4).

    El bucket es compartido con otros sistemas del equipo. Esta clase guarda, lee, lista y borra,
    pero siempre dentro de su propio prefijo: ninguna operación alcanza un objeto ajeno.
    """

    def __init__(self, *, endpoint_url: str, access_key_id: str, secret_access_key: str, bucket: str, prefijo: str,
                 region: str = "auto", cliente: Any = None):
        self.prefijo = prefijo.strip().strip("/")
        if not self.prefijo:
            raise ValueError("R2_PREFIJO es obligatorio: el bucket es compartido y cada sistema trabaja en su propia carpeta")
        if not bucket:
            raise ValueError("R2_BUCKET_NAME es obligatorio")
        self.bucket = bucket
        if cliente is not None:
            self._cliente = cliente
            return
        destino = urlsplit(endpoint_url)
        if destino.scheme != "https" or not (destino.hostname or "").endswith(".r2.cloudflarestorage.com") or not access_key_id or not secret_access_key:
            raise ValueError("R2 mal configurado: revisa R2_ENDPOINT_URL (https://<cuenta>.r2.cloudflarestorage.com), R2_ACCESS_KEY_ID y R2_SECRET_ACCESS_KEY")
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415

        self._cliente = boto3.client(
            "s3", endpoint_url=endpoint_url.rstrip("/"), aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key, region_name=region,
            # R2 no acepta las sumas de verificación que las versiones recientes del SDK agregan por defecto.
            config=Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 2}, signature_version="s3v4",
                          request_checksum_calculation="when_required", response_checksum_validation="when_required"),
        )

    def _clave(self, ruta: str) -> str:
        partes = PurePosixPath(ruta.replace("\\", "/")).parts
        if ruta.startswith("/") or ".." in partes or not partes:
            raise ValueError(f"Ruta fuera del prefijo: {ruta}")
        return "/".join((self.prefijo, *partes))

    def guardar(self, ruta: str, contenido: bytes, content_type: str = "application/octet-stream") -> None:
        self._cliente.put_object(Bucket=self.bucket, Key=self._clave(ruta), Body=contenido, ContentType=content_type)

    def leer(self, ruta: str) -> bytes:
        clave = self._clave(ruta)
        try:
            respuesta = self._cliente.get_object(Bucket=self.bucket, Key=clave)
        except Exception as error:  # noqa: BLE001 - el SDK se importa al usarse; se distingue por el código de la respuesta
            codigo = getattr(error, "response", {}).get("Error", {}).get("Code")
            if codigo in ("NoSuchKey", "404"):
                raise FileNotFoundError(clave) from error
            raise OSError(f"R2 no respondió al leer {clave}") from error
        return respuesta["Body"].read()

    def borrar(self, ruta: str) -> None:
        self._cliente.delete_object(Bucket=self.bucket, Key=self._clave(ruta))

    def listar(self, prefijo: str = "") -> list[ObjetoGuardado]:
        # Sin prefijo se lista la carpeta propia; la barra final evita alcanzar carpetas vecinas (mediflow-triaje-otro/).
        inicio = self._clave(prefijo) if prefijo.strip("/") else f"{self.prefijo}/"
        objetos: list[ObjetoGuardado] = []
        continuacion = None
        while True:
            argumentos = {"Bucket": self.bucket, "Prefix": inicio}
            if continuacion:
                argumentos["ContinuationToken"] = continuacion
            pagina = self._cliente.list_objects_v2(**argumentos)
            for o in pagina.get("Contents", []):
                objetos.append(ObjetoGuardado(o["Key"][len(self.prefijo) + 1:], o["LastModified"], o.get("Size", 0)))
            continuacion = pagina.get("NextContinuationToken")
            if not pagina.get("IsTruncated") or not continuacion:
                return objetos


CONTENT_TYPES = {"txt": "text/plain; charset=utf-8", "pdf": "application/pdf", "json": "application/json"}
