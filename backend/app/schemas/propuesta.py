"""Lo que el LLM propone. No es el JSON final del brief: es la entrada de las reglas
determinísticas (paso 8), que calculan NEWS2, fijan la prioridad (RN-D8), deciden la
revisión humana y enrutan (RN-E). Por eso aquí no hay NEWS2_total, enrutamiento ni
notificación.

`extra="forbid"`: una respuesta con campos inventados es fallo (RN-P3).
"""
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.resultado import Dominio, NivelPrioridad, Setting, TipoDocumento


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClasificacionPropuesta(_Estricto):
    tipo: TipoDocumento
    setting: Setting
    especialidad: str
    dominio: Dominio
    rol_autor: str | None = None  # RN-B2
    score_confianza: float = Field(..., ge=0.0, le=1.0)
    nivel_prioridad_propuesto: NivelPrioridad  # el código puede subirla, nunca bajarla (RN-D8)


class DocumentoPacientePropuesto(_Estricto):
    tipo: str | None = None  # CC, TI, RC, CE, PA, PT, CN, CD, SC, DE, MS, AS o null
    valor: str | None = None  # token [ID_n] o texto tal cual


class PacientePropuesto(_Estricto):
    nombre: str | None = None  # token [PACIENTE_n]
    edad: int | None = None
    sexo: str | None = None
    documento: DocumentoPacientePropuesto = Field(default_factory=DocumentoPacientePropuesto)


class ProfesionalPropuesto(_Estricto):
    nombre: str | None = None  # token [PROFESIONAL_n]
    registro_profesional: str | None = None
    tipo_documento: str | None = None
    numero_documento: str | None = None


class SignosVitalesPropuestos(_Estricto):
    """RN-C2. Solo lo que dice el documento; NEWS2 lo calcula el código (RN-D5)."""

    FR: int | None = None
    SpO2: int | None = None
    FC: int | None = None
    PAS: int | None = None
    Temp: float | None = None
    nivel_conciencia: str | None = None  # alerta | confuso | somnoliento | inconsciente | null


class DiagnosticoPropuesto(_Estricto):
    texto: str
    cie10_sugerido: str | None = None
    cie11_sugerido: str | None = None


class ProcedimientoPropuesto(_Estricto):
    texto: str
    cups: str | None = None


class MedicamentoPropuesto(_Estricto):
    """RN-CO8: campos de la fórmula médica. Las dosis se copian tal cual (RN-CO10 las lee el código)."""

    dci: str
    dosis: str | None = None
    concentracion: str | None = None
    forma_farmaceutica: str | None = None
    via: str | None = None
    frecuencia: str | None = None
    duracion: str | None = None
    cantidad_numeros: str | None = None
    cantidad_letras: str | None = None
    unidades_por_toma: str | None = None  # "2 tabletas", "1 tableta con alimentos": cuántas unidades en cada toma


class ExtraccionPropuesta(_Estricto):
    paciente: PacientePropuesto = Field(default_factory=PacientePropuesto)
    profesional: ProfesionalPropuesto = Field(default_factory=ProfesionalPropuesto)
    fecha_documento: str | None = None  # token [FECHA_n] o dd/mm/aaaa
    signos_vitales: SignosVitalesPropuestos = Field(default_factory=SignosVitalesPropuestos)
    diagnosticos: list[DiagnosticoPropuesto] = Field(default_factory=list)
    procedimientos: list[ProcedimientoPropuesto] = Field(default_factory=list)
    medicamentos: list[MedicamentoPropuesto] = Field(default_factory=list)
    hallazgos_criticos_detectados: list[str] = Field(default_factory=list)  # conceptos de RN-D1
    cobertura_detectada: str | None = None  # RN-A10
    justificacion_clinica: str | None = None  # RN-E5: síntomas, hallazgos previos


class CondicionesEspeciales(_Estricto):
    epoc_hipercapnico: bool = False  # RN-D4
    embarazo: bool = False  # RN-N2
    menor_de_16: bool = False  # RN-N1
    recetario_oficial: bool | None = None  # RN-CO9
    triage_urgencias: str | None = None  # RN-CO16: I a V
    porcentaje_ilegible: float = 0.0  # RN-C5


class ConfianzasPorCampo(_Estricto):
    """RN-C3: cada campo tiene su propio umbral (sección 7)."""

    identidad_paciente: float | None = None
    medicamento_dosis: float | None = None
    diagnostico_codigo: float | None = None
    profesional: float | None = None


class PropuestaLLM(_Estricto):
    clasificacion: ClasificacionPropuesta
    extraccion: ExtraccionPropuesta
    condiciones: CondicionesEspeciales = Field(default_factory=CondicionesEspeciales)
    confianzas: ConfianzasPorCampo = Field(default_factory=ConfianzasPorCampo)
    campos_dudosos: list[str] = Field(default_factory=list)
