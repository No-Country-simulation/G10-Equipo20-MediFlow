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
    tamano_maximo_bytes: int = 10_000_000  # RN-O5
    url_base_documentos: str = "http://localhost:8000/documentos"  # enlace de las alertas (RN-Q4)
    storage_local_dir: str = "./storage"  # respaldo local cuando OCI no está configurado
    oci_namespace: str = ""
    oci_bucket: str = ""
    oci_region: str = ""
    # Almacenamiento: "r2" usa el bucket de Cloudflare R2 del equipo; vacío deja la regla de siempre (OCI si está configurado, si no local).
    storage_backend: str = ""
    r2_endpoint_url: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    r2_region: str = "auto"
    r2_prefijo: str = "mediflow-triaje"  # carpeta propia dentro del bucket compartido
    # LLM externo (RN-M10). La clave nunca se versiona. Proveedor por defecto: OpenAI (decisión 2 del docx).
    llm_proveedor: str = "openai"  # openai | gemini
    openai_api_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    max_paginas_pdf: int = 20  # RN-O5
    openai_model: str = "gpt-4.1-mini"
    openai_timeout_s: float = 60.0
    llm_max_intentos: int = 3  # RN-P2
    prompt_version: str = "triaje_v1"  # RN-R5
    # RN-S3: requisitos declarativos de la instalación. Se completan en .env antes de producción.
    base_legal_tratamiento: str = ""  # RN-M8
    contrato_transmision_internacional: bool = False  # RN-CO19
    # RN-K5: con true, nada se consulta ni se firma sin iniciar sesión. En false (demostración) quien no tiene
    # cuenta con clave sigue firmando con su nombre, y una cuenta con clave solo firma con su sesión.
    exigir_sesion: bool = False
    admin_usuario: str = "admin"  # primera cuenta de administrador: python -m scripts.crear_administrador
    admin_clave_inicial: str = ""
    # Entrega real de notificaciones (RN-F1, RN-F3, RN-Q4). Vacío = NotificadorNulo (no se envía nada,
    # la alerta solo queda en la base). Slack: Incoming Webhook de https://api.slack.com/apps.
    slack_webhook_url: str = ""           # Crítico (RN-F1) -- un Incoming Webhook, un canal
    slack_webhook_url_urgente: str = ""   # Urgente, si se decide avisar por Slack en vez de correo (RN-F3).
                                           # Vacío: usa slack_webhook_url (mismo canal) si tampoco hay SMTP.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_usuario: str = ""
    smtp_clave: str = ""
    smtp_remitente: str = ""
    smtp_destino_urgente: str = ""  # casilla de respaldo: el dato aún no guarda el correo real del profesional


@lru_cache
def get_settings() -> Settings:
    return Settings()
