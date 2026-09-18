import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import URL


class Settings(BaseModel):
    postgres_host: str = "db"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "mediflow"
    postgres_user: str = "mediflow"
    postgres_password: SecretStr
    documents_dir: Path = Path("/data/documents")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)

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
