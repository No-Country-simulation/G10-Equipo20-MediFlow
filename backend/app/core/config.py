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
    tiempo_maximo_documento_s: float = 180.0  # RN-P5: superado, el documento cuenta como fallo técnico
    # RN-T1: llamadas al LLM por periodo (0 = sin límite). Agotado, la extracción no crítica se detiene.
    llm_limite_llamadas_por_periodo: int = 0
    llm_periodo_h: float = 24.0
    limite_documentos_por_minuto: int = 0  # RN-T2 (0 = sin límite)
    escalamiento_cada_s: int = 60  # RN-F2: cada cuánto se revisan las alertas sin acuse (0 = solo por script)
    prompt_version: str = "triaje_v1"  # RN-R5
    # RN-S3: requisitos declarativos de la instalación. Se completan en .env antes de producción.
    base_legal_tratamiento: str = ""  # RN-M8
    contrato_transmision_internacional: bool = False  # RN-CO19
    # RN-K5: nada se consulta ni se firma sin iniciar sesión. No hay modo sin sesión.
    nombre_sede: str = "Sede principal"  # lo que la barra lateral muestra bajo el logo
    clave_minima: int = 10  # política de claves: largo mínimo; además letras y números, y distinta del usuario
    intentos_maximos: int = 5  # intentos fallidos seguidos antes de bloquear la cuenta
    bloqueo_min: int = 15  # minutos de bloqueo tras agotar los intentos
    admin_usuario: str = "admin"  # primera cuenta de administrador: python -m scripts.crear_administrador
    admin_clave_inicial: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
