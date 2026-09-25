import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import URL


class Settings(BaseModel):
    postgres_host: str = "db"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "mediflow"
    postgres_user: str = "mediflow"
    postgres_password: SecretStr
    documents_dir: Path = Path("/data/documents")
    storage_backend: Literal["local", "r2"] = "local"
    r2_endpoint_url: str = ""
    r2_access_key_id: SecretStr = SecretStr("")
    r2_secret_access_key: SecretStr = SecretStr("")
    r2_bucket_name: str = "mediflow-g10"
    r2_region: str = "auto"
    default_country: Literal["EC"] = "EC"
    app_timezone: Literal["America/Guayaquil"] = "America/Guayaquil"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_timeout_seconds: int = Field(default=90, ge=1, le=180)
    processing_max_pages: int = Field(default=20, ge=1, le=100)
    processing_max_characters: int = Field(default=50000, ge=100, le=200000)
    pdf_timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_processing_attempts: int = Field(default=3, ge=1, le=10)

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    # Compose proporciona estas variables; nunca se carga .env desde la imagen.
    return Settings.model_validate({
        field: os.environ[field.upper()]
        for field in Settings.model_fields
        if field.upper() in os.environ
    })
