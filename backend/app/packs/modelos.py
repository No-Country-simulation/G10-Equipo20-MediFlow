"""Forma de un pack de país (sección 4.2) y de los umbrales (sección 7).

Todos los packs tienen la misma forma. Estos modelos validan el YAML al cargarlo,
así un pack mal escrito falla al arrancar y no en medio de un triaje.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EstadoDato = Literal["verificado", "verificado_en_parte", "por_confirmar"]


class Formato(BaseModel):
    separador_decimal: str = Field(..., min_length=1, max_length=1)
    separador_miles: str = Field(..., min_length=1, max_length=1)
    formato_fecha: str


class TipoDocumentoPack(BaseModel):
    nombre: str
    patron: str | None = None  # None: solo se valida presencia
    estado: EstadoDato
    nacional: bool = False  # solo los nacionales se evalúan por edad (RN-CO2)
    no_identificado: bool = False  # MS y AS (RN-CO3)


class RangoEdad(BaseModel):
    edad_min: int = 0
    edad_max: int | None = None


class IdentidadPaciente(BaseModel):
    digito_verificador_personas: bool
    tolerancia_edad_anios: int = 1
    tipos: dict[str, TipoDocumentoPack]
    rangos_edad: dict[str, RangoEdad] = Field(default_factory=dict)


class VerificacionEnLinea(BaseModel):
    disponible: bool
    automatica: bool = False
    url: str | None = None


class IdentidadProfesional(BaseModel):
    registro: str
    ambito: str
    exige_jurisdiccion: bool
    verificacion_en_linea: VerificacionEnLinea


class Terminologia(BaseModel):
    diagnosticos: Literal["CIE-10", "CIE-11", "dual"]
    fecha_cierre_transicion: str | None = None
    procedimientos: str
    procedimientos_estado: EstadoDato = "verificado_en_parte"
    medicamentos: str = "DCI"
    codigo_medicamento: str | None = None


class HallazgoCritico(BaseModel):
    concepto: str
    cie10: list[str] = Field(default_factory=list)
    cie11: list[str] = Field(default_factory=list)
    sinonimos: list[str] = Field(default_factory=list)
    requiere_signos_tension: bool = False
    estado: EstadoDato = "verificado_en_parte"


class Medicamentos(BaseModel):
    alto_riesgo: list[str]
    control_especial: list[str]
    control_especial_estado: EstadoDato = "verificado_en_parte"


class Cobertura(BaseModel):
    modelo: str
    entidad: str
    estado: EstadoDato


class ProgramaCobertura(BaseModel):
    motivo: str
    estado: EstadoDato
    lista: list[str] = Field(default_factory=list)

    @property
    def activo(self) -> bool:
        # RN-E11: un dato por_confirmar no activa decisiones automáticas.
        return self.estado == "verificado"


class Urgencias(BaseModel):
    autorizacion_previa: bool
    canales_sin_autorizacion: list[str]
    motivo_aviso_auditoria: str
    triage_eleva_prioridad: bool = False  # RN-CO16


class Retencion(BaseModel):
    anios: int
    archivo_gestion_anios: int | None = None
    archivo_central_anios: int | None = None
    norma: str | None = None
    purga_automatica: bool = False


class DatosPersonales(BaseModel):
    norma: str
    datos_salud_sensibles: bool
    llm_es_transmision_internacional: bool
    solo_documentos_sinteticos_en_mvp: bool


class PackPais(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pais: str
    nombre: str
    version_pack: str
    formato: Formato
    identidad_paciente: IdentidadPaciente
    identidad_profesional: IdentidadProfesional
    terminologia: Terminologia
    hallazgos_criticos: list[HallazgoCritico]
    medicamentos: Medicamentos
    coberturas: dict[str, Cobertura]
    programas_cobertura: dict[str, ProgramaCobertura]
    urgencias: Urgencias
    vocabulario: dict[str, list[str]]
    retencion: Retencion
    datos_personales: DatosPersonales


# --- Umbrales (sección 7) ---------------------------------------------------


class UmbralesConfianza(BaseModel):
    clasificacion: float
    identidad_paciente: float
    medicamento_dosis: float
    diagnostico_codigo: float
    profesional: float
    resto: float
    texto_ilegible_max: float | None = None


class UmbralesConsistencia(BaseModel):
    tolerancia_edad_anios: int


class ColaRevision(BaseModel):
    critico_min: int
    urgente_h: int
    rutina_h_habiles: int


class UmbralesTiempo(BaseModel):
    comunicacion_critico_min: int
    escalamiento_sin_acuse_min: int
    atencion_urgente_h: int
    cola_revision: ColaRevision


class UmbralesNews2(BaseModel):
    configurable: Literal[False] = False  # RN-D5: nunca configurable
    fr_bajo: int
    fr_alto: int
    spo2_bajo: int
    spo2_escala2_min: int
    spo2_escala2_max: int
    fc_bajo: int
    fc_alto: int
    pas_bajo: int
    total_critico: int
    edad_minima: int


class Umbrales(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confianza: UmbralesConfianza
    consistencia: UmbralesConsistencia
    tiempos: UmbralesTiempo
    news2: UmbralesNews2

    def supera(self, campo: str, score: float) -> bool:
        """RN-C3: un campo pasa cuando su score es mayor o igual a su umbral."""
        umbral = getattr(self.confianza, campo, None)
        if umbral is None:
            umbral = self.confianza.resto
        return score >= umbral
