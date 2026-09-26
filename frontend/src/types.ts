/** Tipado estricto del pipeline. Espejo del contrato Pydantic del backend (RN-G7). */

export type NivelPrioridad = "Crítico" | "Urgente" | "Rutina";
export type CanalOrigen = "Guardia_Emergencias" | "Consulta_Ambulatoria" | "Hospitalizado" | "Externo";
export type Cobertura = "contributivo" | "subsidiado" | "especial_excepcion" | "soat" | "arl" | "plan_voluntario" | "no_afiliado";
export type EstadoDocumento =
  | "RECIBIDO" | "VALIDADO" | "CLASIFICADO" | "EXTRAIDO" | "EVALUADO" | "EN_REVISION_HUMANA"
  | "RESUELTO" | "ENRUTADO" | "ENTREGADO" | "RECHAZADO" | "FALLO_TECNICO";
export type Destino =
  | "Cola_Emergencia_Medica" | "Auditoria_Autorizaciones" | "Farmacia_Hospitalaria"
  | "Historia_Clinica_Electronica" | "Cola_Revision_Humana" | "Gestion_Programa_Cobertura";

export interface DocumentoRequest {
  documento_id: string;
  canal_origen: CanalOrigen;
  pais_origen?: string;
  cobertura_paciente?: Cobertura | null;
  tipo_contenido: "texto" | "pdf" | "imagen";
  contenido_texto?: string | null;
  archivo_base64?: string | null;
  nombre_archivo?: string | null;
  metadatos?: Record<string, unknown>;
}

export interface Clasificacion {
  tipo: string;
  setting: string;
  especialidad: string;
  dominio: string;
  score_confianza: number;
  nivel_prioridad: NivelPrioridad;
}

export interface Paciente {
  nome: string | null;
  nombre: string | null;
  edad: number | null;
  sexo: string | null;
  documento: { tipo: string; valor: string | null; estado: string };
}

export interface Medicamento {
  dci: string;
  dosis: string | null;
  dosis_valor: string | null;
  via: string | null;
  frecuencia: string | null;
  alto_riesgo: boolean;
  control_especial: boolean;
}

export interface Extraccion {
  paciente: Paciente;
  profesional: { nombre: string | null; registro_profesional: string | null };
  fecha_documento: string | null;
  signos_vitales: { FR: number | null; SpO2: number | null; FC: number | null; PAS: number | null; Temp: number | null; NEWS2_total: number | null };
  diagnosticos: { texto: string; cie10_sugerido: string | null; cie11_sugerido: string | null }[];
  procedimientos: { texto: string; cups: string | null }[];
  medicamentos: Medicamento[];
  hallazgos_criticos_detectados: string[];
}

export interface Enrutamiento {
  destino_principal: Destino;
  destinos_secundarios: Destino[];
  justificacion_enrutamiento: string;
  destinos_tras_revision: Destino[];
  motivos_destino: Record<string, string>;
  entregas_retenidas: Record<string, string>;
  documentacion_incompleta: boolean;
}

export interface Notificacion {
  canal: string;
  destinatario: string;
  mensaje: string;
  fecha_hora: string;
  enlace: string | null;
  estado_acuse: "pendiente" | "acusado" | "escalado";
}

export interface DecisionRegistrada {
  regla: string;
  evidencia: string;
  propuesta_llm: string | null;
  decision: string;
  fecha_hora: string;
}

export interface ResultadoTriaje {
  documento_id: string;
  clasificacion: Clasificacion;
  extraccion: Extraccion;
  evaluacion: { requiere_auditoria_humana: boolean; motivo_auditoria: string | null; campos_dudosos: string[] };
  enrutamiento: Enrutamiento;
  notificacion_generada: Notificacion | null;
  estado: EstadoDocumento;
  pack_pais: string;
  version_reglas: string;
  historial_decisiones: DecisionRegistrada[];
  status_backup: "pendiente" | "ok" | "error";
  ruta_storage: string | null;
  posible_duplicado_de: string | null;
}

export interface Transicion {
  de_estado: EstadoDocumento | null;
  a_estado: EstadoDocumento;
  actor: string;
  motivo: string;
  fecha_hora: string;
}

export interface Alerta {
  nivel: NivelPrioridad;
  canal: string;
  destinatario: string;
  mensaje: string;
  estado_acuse: string;
  acusado_por: string | null;
  emitida_en: string;
}

/** Respuesta de POST /documentos y GET /documentos/{id}. */
export interface DocumentoDetalle {
  documento_id: string;
  version: number;
  estado: EstadoDocumento;
  nivel_prioridad: NivelPrioridad | null;
  tipo_contenido?: "texto" | "pdf" | "imagen";
  formato?: "txt" | "pdf" | "png" | "jpeg" | string | null;
  nombre_archivo?: string | null;
  num_paginas?: number;
  paginas?: { pagina: number; tipo: "texto" | "imagen"; ruta?: string | null }[];
  status_backup: string;
  ruta_storage: string | null;
  posible_duplicado_de: string | null;
  codigo_error: string | null;
  resultado: ResultadoTriaje | null;
  duplicado?: boolean;
  canal_origen?: CanalOrigen;
  pais_origen?: string;
  entregas?: Record<string, boolean>;
  alerta?: Alerta | null;
  correcciones?: { campo: string; extraido: unknown; corregido: unknown; usuario: string }[];
  transiciones?: Transicion[];
}

export interface ItemCola {
  documento_id: string;
  version: number;
  nivel_prioridad: NivelPrioridad | null;
  motivo_auditoria: string | null;
  campos_dudosos: string[];
  tipo: string | null;
  creado_en: string;
  plazo_minutos: number;
}

/** Respuesta de GET /alertas. Nunca lleva datos del paciente (RN-Q4). */
export interface AlertaListada {
  documento_id: string;
  version: number;
  nivel: NivelPrioridad;
  canal: string;
  destinatario: string;
  mensaje: string;
  concepto: string | null;
  emitida_en: string;
  plazo_minutos: number;
  estado_acuse: "pendiente" | "acusado" | "escalado";
  acusado_por: string | null;
  acusado_en: string | null;
  estado_documento: EstadoDocumento;
}

export interface ItemListado {
  documento_id: string;
  version: number;
  estado: EstadoDocumento;
  nivel_prioridad: NivelPrioridad | null;
  tipo_contenido: string;
  formato: string | null;
  nombre_archivo: string | null;
  canal_origen: string;
  creado_en: string | null;
  tipo: string | null;
  motivo_auditoria: string | null;
  codigo_error: string | null;
  num_paginas?: number;
}

export interface Listado {
  items: ItemListado[];
  total: number;
  limit: number;
  offset: number;
}

export interface DatosArchivo {
  documento_id: string;
  canal_origen: CanalOrigen;
  cobertura_paciente?: Cobertura | null;
  pais_origen?: string;
}

export type AccionRevision = "aprobar" | "corregir" | "rechazar";

export interface ResolucionRequest {
  accion: AccionRevision;
  usuario: string;
  rol: string;
  motivo: string;
  correcciones?: Record<string, unknown> | null;
}

export interface RespuestaEntrega {
  documento_id: string;
  estado: EstadoDocumento;
  entregas: Record<string, boolean>;
  retenidas: Record<string, string>;
  pendientes: string[];
}
