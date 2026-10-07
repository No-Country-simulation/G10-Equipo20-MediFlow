from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import logging
import re
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.services.errors import DocumentError

logger = logging.getLogger(__name__)


class R2DocumentStorage:
    backend = "r2"

    def __init__(self, settings, bucket=None):
        self.bucket = bucket or settings.r2_bucket_name
        self.prefix = settings.r2_object_prefix
        endpoint = urlsplit(settings.r2_endpoint_url)
        if (endpoint.scheme != "https" or not endpoint.hostname
                or not endpoint.hostname.endswith(".r2.cloudflarestorage.com")
                or endpoint.username or endpoint.password or endpoint.query
                or endpoint.path not in ("", "/")
                or not settings.r2_access_key_id.get_secret_value()
                or not settings.r2_secret_access_key.get_secret_value()):
            raise OSError("R2_NOT_CONFIGURED")
        self.client = boto3.client(
            "s3", endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.r2_secret_access_key.get_secret_value(),
            region_name=settings.r2_region,
            config=Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 1},
                          signature_version="s3v4", request_checksum_calculation="when_required",
                          response_checksum_validation="when_required"),
        )

    def object_key(self, relative: str) -> str:
        return f"{self.prefix}/{relative}"

    def _check_key(self, key: str, writing: bool = False):
        from app.core.countries import COUNTRY_CODES
        parts = key.split("/")
        if parts[0] == self.prefix:
            parts = parts[1:]
        elif writing:
            raise OSError("R2_KEY_OUTSIDE_PREFIX")
        # Legacy country/originals keys remain readable/deletable through DB references.
        original = (len(parts) == 3 and parts[1] == "originals"
                    and re.fullmatch(r"[A-Za-z0-9_-]+\.(pdf|jpg|png|json)", parts[2]))
        backup = (len(parts) == 5 and parts[1] == "results"
                  and re.fullmatch(r"[0-9a-f-]{36}", parts[2])
                  and parts[3] in ("ENTREGADO", "EN_REVISION_HUMANA", "FALLO_TECNICO", "RECHAZADO", "EVALUADO", "ENRUTADO")
                  and re.fullmatch(r"[0-9a-f-]{36}\.json", parts[4]))
        if (not parts or parts[0] not in COUNTRY_CODES or not (original or backup)):
            raise OSError("R2_KEY_OUTSIDE_PREFIX")

    def put_file(self, key: str, path: Path, max_bytes: int) -> None:
        self._check_key(key, writing=True)
        if path.stat().st_size > max_bytes:
            raise DocumentError(413, "FILE_TOO_LARGE")
        try:
            with path.open("rb") as source:
                self.client.put_object(Bucket=self.bucket, Key=key, Body=source,
                                       ContentType={".pdf": "application/pdf", ".jpg": "image/jpeg", ".png": "image/png", ".json": "application/json"}[path.suffix], IfNoneMatch="*")
        except (BotoCoreError, ClientError) as exc:
            if isinstance(exc, ClientError) and exc.response.get("Error", {}).get("Code") in ("PreconditionFailed", "412"):
                raise OSError("R2_OBJECT_ALREADY_EXISTS") from None
            # A timeout can follow a successful write: clean up only this request's UUID.
            try:
                self.delete(key)
            except OSError:
                logger.error("R2 cleanup requires reconciliation for object %s", key)
            raise OSError("R2_WRITE_FAILED") from None

    def delete(self, key: str) -> None:
        self._check_key(key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError):
            raise OSError("R2_DELETE_FAILED") from None

    def put_snapshot(self, key: str, path: Path) -> None:
        self._check_key(key, writing=True)
        data = path.read_bytes()
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType="application/json", IfNoneMatch="*")
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("PreconditionFailed", "412"):
                # A previous uncertain write may already have stored this exact snapshot.
                try:
                    response = self.client.get_object(Bucket=self.bucket, Key=key)
                except (ClientError, BotoCoreError):
                    raise OSError("R2_SNAPSHOT_FAILED") from None
                try:
                    if response["Body"].read(len(data) + 1) == data:
                        return
                except BotoCoreError:
                    raise OSError("R2_SNAPSHOT_FAILED") from None
                finally:
                    response["Body"].close()
            raise OSError("R2_SNAPSHOT_FAILED") from None
        except BotoCoreError:
            raise OSError("R2_SNAPSHOT_FAILED") from None

    @contextmanager
    def materialize(self, key: str, max_bytes: int):
        self._check_key(key)
        with TemporaryDirectory(prefix="mediflow-r2-") as temporary:
            path = Path(temporary) / Path(key).name
            try:
                response = self.client.get_object(Bucket=self.bucket, Key=key)
                body = response["Body"]
                try:
                    if response["ContentLength"] > max_bytes:
                        raise DocumentError(413, "PROCESSING_FILE_TOO_LARGE")
                    size = 0
                    with path.open("xb") as target:
                        while chunk := body.read(64 * 1024):
                            size += len(chunk)
                            if size > max_bytes:
                                raise DocumentError(413, "PROCESSING_FILE_TOO_LARGE")
                            target.write(chunk)
                    if size != response["ContentLength"]:
                        raise OSError("R2_INCOMPLETE_READ")
                finally:
                    body.close()
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    raise DocumentError(422, "DOCUMENT_FILE_MISSING") from None
                raise OSError("R2_READ_FAILED") from None
            except BotoCoreError:
                raise OSError("R2_READ_FAILED") from None
            yield path
