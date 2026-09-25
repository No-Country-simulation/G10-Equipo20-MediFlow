"""Contrato de entrada del agente (dominio A: ingesta e identificación)."""
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CanalOrigen(StrEnum):
    """RN-A9: canal_origen es obligatorio y afecta el enrutamiento."""

    GUARDIA_EMERGENCIAS = "Guardia_Emergencias"
    CONSULTA_AMBULATORIA = "Consulta_Ambulatoria"
    HOSPITALIZADO = "Hospitalizado"
    EXTERNO = "Externo"


class CoberturaPaciente(StrEnum):
    """RN-CO12: valores de cobertura_paciente en Colombia."""

    CONTRIBUTIVO = "contributivo"
    SUBSIDIADO = "subsidiado"
    ESPECIAL_EXCEPCION = "especial_excepcion"
    SOAT = "soat"
    ARL = "arl"
    PLAN_VOLUNTARIO = "plan_voluntario"
    NO_AFILIADO = "no_afiliado"


class TipoContenido(StrEnum):
    """RN-A1: formatos aceptados."""

    TEXTO = "texto"
    PDF = "pdf"
    IMAGEN = "imagen"


class DocumentoRequest(BaseModel):
    # RN-G7: se aceptan campos extra del brief sin rechazar el request.
    model_config = ConfigDict(extra="allow")

    documento_id: str = Field(..., min_length=1, description="RN-A2: obligatorio y único")
    canal_origen: CanalOrigen = Field(..., description="RN-A9")
    pais_origen: str = Field(
        default="CO",
        min_length=2,
        max_length=2,
        description="RN-A3: si falta se usa el país de la instalación; nunca se infiere del texto",
    )
    cobertura_paciente: CoberturaPaciente | None = Field(default=None, description="RN-A10")
    tipo_contenido: TipoContenido = Field(..., description="RN-A1")
    contenido_texto: str | None = None
    archivo_base64: str | None = None
    nombre_archivo: str | None = None
    metadatos: dict[str, Any] = Field(default_factory=dict)

    @field_validator("documento_id")
    @classmethod
    def documento_id_no_vacio(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("RN-A2: documento_id no puede estar vacío")
        return valor

    @field_validator("pais_origen")
    @classmethod
    def pais_en_mayusculas(cls, valor: str) -> str:
        return valor.upper()

    @model_validator(mode="after")
    def contenido_coherente_con_tipo(self) -> "DocumentoRequest":
        if self.tipo_contenido is TipoContenido.TEXTO:
            if not (self.contenido_texto and self.contenido_texto.strip()):
                raise ValueError("RN-A1: un documento de texto exige contenido_texto")
        elif not self.archivo_base64:
            raise ValueError("RN-A1: PDF e imagen exigen archivo_base64")
        return self
