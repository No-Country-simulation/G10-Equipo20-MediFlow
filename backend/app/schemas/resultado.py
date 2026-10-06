"""Contrato de salida del agente: el JSON de resultado.

Respeta los nombres de campo del brief y solo agrega campos (RN-G7). Las dos
desviaciones deliberadas están en la sección 1.3 del documento de reglas:
la alerta no lleva datos del paciente (RN-Q4) y el TEP es Crítico (opción A).

Las invariantes que se validan aquí son las que ninguna salida puede violar,
sin importar qué haya propuesto el LLM: RN-D8, RN-E3, RN-E8, RN-F1, RN-G7, RN-Q4.
"""
import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

FORMATO_FECHA_CO = re.compile(r"^\d{2}/\d{2}/\d{4}$")  # RN-CO11


# --- Enumeraciones cerradas -------------------------------------------------


class TipoDocumento(StrEnum):
    """RN-B1."""

    RECETA = "Receta Médica"
    IMAGENES = "Informe de Imágenes"
    LABORATORIO = "Informe de Laboratorio"
    ORDEN_PROCEDIMIENTO = "Orden de Procedimiento"
    EPICRISIS = "Epicrisis o Alta"
    CERTIFICADO = "Certificado Médico"
    NO_CLASIFICABLE = "No Clasificable"


class Setting(StrEnum):
    """RN-B2."""

    AMBULATORIO = "ambulatorio"
    HOSPITALIZADO = "hospitalizado"
    URGENCIA = "urgencia"


class Dominio(StrEnum):
    """RN-B2."""

    CARDIOLOGIA = "Cardiología"
    NEUMOLOGIA = "Neumología"
    MIXTO = "Mixto"
    OTRO = "Otro"


class NivelPrioridad(StrEnum):
    """RN-D1, RN-D6, RN-D7. Opción A de la sección 2.2."""

    CRITICO = "Crítico"
    URGENTE = "Urgente"
    RUTINA = "Rutina"


class TipoDocumentoPaciente(StrEnum):
    """RN-CO1. MS y AS no son documentos: activan RN-CO3."""

    CC = "CC"
    TI = "TI"
    RC = "RC"
    CE = "CE"
    PA = "PA"
    PT = "PT"
    CN = "CN"
    CD = "CD"
    SC = "SC"
    DE = "DE"
    MS = "MS"
    AS = "AS"
    AUSENTE = "ausente"


class EstadoIdentidad(StrEnum):
    """RN-A4."""

    VALIDO_VERIFICADO = "valido_verificado"
    VALIDO_FORMATO = "valido_formato"
    AUSENTE = "ausente"
    INVALIDO = "invalido"


class MotivoAuditoria(StrEnum):
    """Motivos cerrados de derivación a revisión humana."""

    RECETA_INCOMPLETA_NORMA = "receta_incompleta_norma"  # RN-CO8
    CONTROL_ESPECIAL_SIN_RECETARIO = "control_especial_sin_recetario"  # RN-CO9
    COBERTURA_NO_INFORMADA = "cobertura_no_informada"  # RN-E10
    COBERTURA_NO_CONFIGURADA = "cobertura_no_configurada"  # RN-E11
    FUERA_DE_ALCANCE = "fuera_de_alcance"  # RN-B3
    FALLO_TECNICO = "fallo_tecnico"  # RN-P2
    DOCUMENTACION_INCOMPLETA = "documentacion_incompleta"  # RN-E5
    CLASIFICACION_BAJA_CONFIANZA = "clasificacion_baja_confianza"  # RN-B4
    NO_CLASIFICABLE = "no_clasificable"  # RN-B4
    CAMPO_DUDOSO = "campo_dudoso"  # RN-C3
    AMBIGUO = "ambiguo"  # RN-C4
    ILEGIBLE = "ilegible"  # RN-C5
    DOSIS_AMBIGUA = "dosis_ambigua"  # RN-CO10
    FECHA_AMBIGUA = "fecha_ambigua"  # RN-C8
    IDENTIDAD_INVALIDA = "identidad_invalida"  # RN-A4
    PROFESIONAL_NO_IDENTIFICABLE = "profesional_no_identificable"  # RN-A8
    SIGNOS_VITALES_SIN_ESCALA = "signos_vitales_sin_escala"  # RN-N1, RN-N2, RN-N4
    CRITICO_BAJA_CONFIANZA = "critico_baja_confianza"  # RN-D9
    CAMPO_OBLIGATORIO_FALTANTE = "campo_obligatorio_faltante"  # RN-C1
    DESTINO_INACTIVO = "destino_inactivo"  # RN-L1
    IDENTIDAD_EN_CONFLICTO = "identidad_en_conflicto"  # RN-A4: el documento ya está registrado con otro nombre


class Destino(StrEnum):
    """RN-E1."""

    COLA_EMERGENCIA_MEDICA = "Cola_Emergencia_Medica"
    AUDITORIA_AUTORIZACIONES = "Auditoria_Autorizaciones"
    FARMACIA_HOSPITALARIA = "Farmacia_Hospitalaria"
    HISTORIA_CLINICA_ELECTRONICA = "Historia_Clinica_Electronica"
    COLA_REVISION_HUMANA = "Cola_Revision_Humana"
    GESTION_PROGRAMA_COBERTURA = "Gestion_Programa_Cobertura"


class EstadoDocumento(StrEnum):
    """Sección 3.1 y RN-I1."""

    RECIBIDO = "RECIBIDO"
    VALIDADO = "VALIDADO"
    CLASIFICADO = "CLASIFICADO"
    EXTRAIDO = "EXTRAIDO"
    EVALUADO = "EVALUADO"
    EN_REVISION_HUMANA = "EN_REVISION_HUMANA"
    RESUELTO = "RESUELTO"
    ENRUTADO = "ENRUTADO"
    ENTREGADO = "ENTREGADO"
    RECHAZADO = "RECHAZADO"
    FALLO_TECNICO = "FALLO_TECNICO"


# --- Bloques del JSON -------------------------------------------------------


class Clasificacion(BaseModel):
    tipo: TipoDocumento
    setting: Setting
    especialidad: str
    dominio: Dominio
    score_confianza: float = Field(..., ge=0.0, le=1.0)
    nivel_prioridad: NivelPrioridad


class DocumentoPaciente(BaseModel):
    tipo: TipoDocumentoPaciente = TipoDocumentoPaciente.AUSENTE
    valor: str | None = None
    estado: EstadoIdentidad = EstadoIdentidad.AUSENTE


class Paciente(BaseModel):
    """RN-G7: el brief usa `nome`; se agrega `nombre` con el mismo valor."""

    nome: str | None = None
    nombre: str | None = None
    nombre_token: str | None = None
    edad: int | None = Field(default=None, ge=0, le=130)
    sexo: str | None = None
    documento: DocumentoPaciente = Field(default_factory=DocumentoPaciente)

    @model_validator(mode="after")
    def nome_y_nombre_espejo(self) -> "Paciente":
        if self.nome is None and self.nombre is None:
            return self
        if self.nome is None:
            self.nome = self.nombre
        elif self.nombre is None:
            self.nombre = self.nome
        elif self.nome != self.nombre:
            raise ValueError("RN-G7: paciente.nome y paciente.nombre deben tener el mismo valor")
        return self


class VerificacionProfesional(BaseModel):
    """RN-A7: qué dijo la verificación del profesional. Donde no existe, no_aplica y no penaliza el score."""

    estado: Literal["verificado", "no_encontrado", "sin_datos", "no_aplica"]
    fuente: str | None = None  # padrón de profesionales de la instalación
    detalle: str = ""
    enlace_consulta: str | None = None  # consulta pública del registro (ReTHUS) para el revisor
    consultado_en_registro_en: str | None = None  # última consulta manual en el registro nacional, si se anotó


class Profesional(BaseModel):
    """RN-A6, RN-CO5."""

    nombre_token: str | None = None
    nombre: str | None = None
    registro_profesional: str | None = None
    tipo_documento: str | None = None
    numero_documento: str | None = None
    jurisdiccion: str = "no_aplica"
    verificacion: VerificacionProfesional | None = None  # RN-A7


class SignosVitales(BaseModel):
    """RN-C2. NEWS2_total lo calcula el código, nunca el LLM (RN-D5, RN-D8)."""

    FR: int | None = None
    SpO2: int | None = None
    FC: int | None = None
    PAS: int | None = None
    Temp: float | None = None
    nivel_conciencia: str | None = None
    NEWS2_total: int | None = None


class Diagnostico(BaseModel):
    texto: str
    cie10_sugerido: str | None = None
    cie11_sugerido: str | None = None


class Procedimiento(BaseModel):
    texto: str
    cups: str | None = None


class Medicamento(BaseModel):
    dci: str
    dosis: str | None = None
    dosis_valor: str | None = None  # cantidad leída con los separadores del pack (RN-CO10)
    concentracion: str | None = None
    forma_farmaceutica: str | None = None
    via: str | None = None
    frecuencia: str | None = None
    duracion: str | None = None
    cantidad_numeros: str | None = None
    cantidad_letras: str | None = None
    alto_riesgo: bool = False
    control_especial: bool = False


class Extraccion(BaseModel):
    paciente: Paciente = Field(default_factory=Paciente)
    profesional: Profesional = Field(default_factory=Profesional)
    fecha_documento: str | None = None
    signos_vitales: SignosVitales = Field(default_factory=SignosVitales)
    diagnosticos: list[Diagnostico] = Field(default_factory=list)
    procedimientos: list[Procedimiento] = Field(default_factory=list)
    medicamentos: list[Medicamento] = Field(default_factory=list)
    hallazgos_criticos_detectados: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def fecha_en_formato_del_pack(self) -> "Extraccion":
        if self.fecha_documento is not None and not FORMATO_FECHA_CO.match(self.fecha_documento):
            raise ValueError("RN-CO11: fecha_documento debe ser dd/mm/aaaa")
        return self


class Evaluacion(BaseModel):
    requiere_auditoria_humana: bool
    motivo_auditoria: MotivoAuditoria | None = None
    campos_dudosos: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def motivo_coherente(self) -> "Evaluacion":
        if self.requiere_auditoria_humana and self.motivo_auditoria is None:
            raise ValueError("requiere_auditoria_humana exige motivo_auditoria")
        if not self.requiere_auditoria_humana and self.motivo_auditoria is not None:
            raise ValueError("motivo_auditoria solo aplica cuando requiere_auditoria_humana es true")
        return self


class Enrutamiento(BaseModel):
    destino_principal: Destino
    destinos_secundarios: list[Destino] = Field(default_factory=list)
    justificacion_enrutamiento: str
    # Campos agregados (RN-G7 permite agregar)
    destinos_tras_revision: list[Destino] = Field(default_factory=list)  # RN-E8: plan al salir de la cola
    motivos_destino: dict[str, str] = Field(default_factory=dict)  # RN-CO13, RN-E5, RN-E9: motivo por destino
    entregas_retenidas: dict[str, str] = Field(default_factory=dict)  # RN-A4, RN-N3: destinos retenidos y por qué
    documentacion_incompleta: bool = False  # RN-E5

    @model_validator(mode="after")
    def principal_no_repetido(self) -> "Enrutamiento":
        if self.destino_principal in self.destinos_secundarios:
            raise ValueError("RN-E3: destino_principal no puede estar en destinos_secundarios")
        return self


class Notificacion(BaseModel):
    """RN-F1, RN-Q4."""

    canal: Literal["Slack", "Correo", "SMS"]
    destinatario: str
    mensaje: str
    fecha_hora: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    enlace: str | None = None
    estado_acuse: Literal["pendiente", "acusado", "escalado"] = "pendiente"


class DecisionRegistrada(BaseModel):
    """RN-G2: qué regla se disparó, con qué evidencia, qué dijo el LLM y qué se decidió."""

    regla: str
    evidencia: str
    propuesta_llm: str | None = None
    decision: str
    fecha_hora: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- Resultado completo -----------------------------------------------------


class ResultadoTriaje(BaseModel):
    documento_id: str
    clasificacion: Clasificacion
    extraccion: Extraccion
    evaluacion: Evaluacion
    enrutamiento: Enrutamiento
    notificacion_generada: Notificacion | None = None

    # Campos agregados (RN-G7 permite agregar)
    estado: EstadoDocumento = EstadoDocumento.EVALUADO
    pack_pais: str = "CO"  # RN-G6
    version_reglas: str = "8"  # RN-G6
    historial_decisiones: list[DecisionRegistrada] = Field(default_factory=list)  # RN-G2
    status_backup: Literal["pendiente", "ok", "error"] = "pendiente"  # RN-G3
    ruta_storage: str | None = None  # RN-G1
    posible_duplicado_de: str | None = None  # RN-O3

    @model_validator(mode="after")
    def invariantes_del_nucleo(self) -> "ResultadoTriaje":
        self._critico_por_hallazgo()
        self._critico_con_alerta()
        self._auditoria_pasa_por_cola()
        self._alerta_sin_datos_del_paciente()
        return self

    def _critico_por_hallazgo(self) -> None:
        # RN-D8: un hallazgo crítico fija la prioridad mínima en Crítico.
        if self.extraccion.hallazgos_criticos_detectados and (
            self.clasificacion.nivel_prioridad is not NivelPrioridad.CRITICO
        ):
            raise ValueError(
                "RN-D8: hay hallazgos críticos detectados; la prioridad mínima es Crítico"
            )

    def _critico_con_alerta(self) -> None:
        # RN-F1: todo caso Crítico genera notificacion_generada.
        if self.clasificacion.nivel_prioridad is NivelPrioridad.CRITICO and self.notificacion_generada is None:
            raise ValueError("RN-F1: un caso Crítico exige notificacion_generada")

    def _auditoria_pasa_por_cola(self) -> None:
        # RN-E8: nada con revisión humana llega a un destino final sin pasar por la cola.
        if self.evaluacion.requiere_auditoria_humana and (
            self.enrutamiento.destino_principal is not Destino.COLA_REVISION_HUMANA
        ):
            raise ValueError(
                "RN-E8: con requiere_auditoria_humana el destino_principal es Cola_Revision_Humana"
            )

    def _alerta_sin_datos_del_paciente(self) -> None:
        # RN-Q4: la alerta solo lleva ID de documento, nivel y enlace.
        if self.notificacion_generada is None:
            return
        mensaje = self.notificacion_generada.mensaje.casefold()
        paciente = self.extraccion.paciente
        prohibidos: list[str] = []
        if paciente.nombre:
            prohibidos.append(paciente.nombre)
            prohibidos.extend(p for p in paciente.nombre.split() if len(p) >= 3)
        if paciente.documento.valor:
            prohibidos.append(paciente.documento.valor)
        for dato in prohibidos:
            if dato.casefold() in mensaje:
                raise ValueError("RN-Q4: la notificación no puede llevar datos del paciente")
