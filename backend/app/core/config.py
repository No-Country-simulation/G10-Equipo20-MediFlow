"""Configuración de la instalación (RN-S1, RN-S2).

Los valores vienen de variables de entorno o de .env. Nada clínico vive aquí:
los umbrales y el pack de país se cargan desde archivos de configuración (sección 7).
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MediFlow"
    pais_instalacion: str = "CO"  # RN-S2: país por defecto de la instalación
    version_reglas: str = "8"  # RN-G6: versión del documento de reglas de negocio
    database_url: str = "postgresql+psycopg://mediflow:mediflow@localhost:5432/mediflow"


@lru_cache
def get_settings() -> Settings:
    return Settings()
