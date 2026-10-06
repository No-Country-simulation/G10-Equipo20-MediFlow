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

/** RN-A7: resultado de verificar al profesional contra el padrón de la instalación. */
export interface VerificacionProfesional {
  estado: "verificado" | "no_encontrado" | "sin_datos" | "no_aplica";
  fuente: string | null;
  detalle: string;
  enlace_consulta: string | null;
  consultado_en_registro_en: string | null;
}

export interface Extraccion {
  paciente: Paciente;
  profesional: { nombre: string | null; registro_profesional: string | null; verificacion?: VerificacionProfesional | null };
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
  confianzas?: Partial<Record<"identidad_paciente" | "medicamento_dosis" | "diagnostico_codigo" | "profesional", number | null>>;
  umbrales?: Partial<Record<"clasificacion" | "identidad_paciente" | "medicamento_dosis" | "diagnostico_codigo" | "profesional" | "resto", number>>;
  texto_enviado_llm?: string | null;
  asignado_a?: string | null;
  escalado_a_rol?: string | null;
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
  verificaciones?: { orden: number; usuario: string; fecha_hora?: string }[];
  autorizacion?: Autorizacion | null;
  /** Ficha del directorio de pacientes a la que quedó vinculado (RN-M6). */
  paciente_id?: number | null;
  /** RN-M6: solicitud del titular pendiente de respuesta sobre este documento. */
  solicitud_titular?: SolicitudTitular | null;
  /** RN-O4: id del PDF compuesto del que esta parte salió. */
  documento_padre?: string | null;
  /** RN-O4: las partes de un PDF compuesto; solo las trae el padre. */
  sub_documentos?: ItemListado[];
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
  /** Conceptos críticos del pack (TEP_AGUDO…), para ver qué es cada caso sin abrirlo. */
  hallazgos?: string[];
  /** RN-J3: revisor que tiene el caso. RN-J2/RN-J3: rol al que escaló. */
  asignado_a?: string | null;
  escalado_a_rol?: string | null;
}

/** RN-J3: a quién se puede reasignar un caso. */
export interface Revisor {
  usuario: string;
  nombre: string;
  rol: string;
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
  /** RN-O4: id del PDF compuesto del que esta parte salió. */
  documento_padre?: string | null;
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
  /** RN-O4: páginas de cada sub-documento de un PDF compuesto, p. ej. "1-2,3". */
  paginas_por_documento?: string | null;
}

export type AccionRevision = "aprobar" | "corregir" | "rechazar" | "transcribir" | "reasignar" | "escalar";

export interface ResolucionRequest {
  accion: AccionRevision;
  motivo: string;
  correcciones?: Record<string, unknown> | null;
  /** reasignar: cuenta del revisor que toma el caso (RN-J3). */
  asignar_a?: string | null;
  /** Fallo técnico: la persona transcribe con la misma forma que la propuesta del LLM. */
  transcripcion?: Record<string, unknown> | null;
}

export interface RespuestaEntrega {
  documento_id: string;
  estado: EstadoDocumento;
  entregas: Record<string, boolean>;
  retenidas: Record<string, string>;
  pendientes: string[];
}

/** Fase C: Farmacia, Autorizaciones y resumen. */
export interface RecetaPorVerificar {
  documento_id: string;
  version: number;
  nivel_prioridad: NivelPrioridad | null;
  creado_en: string | null;
  medicamentos: Medicamento[];
  alto_riesgo: boolean;
  control_especial: boolean;
  verificaciones_requeridas: number;
  verificaciones: { orden: number; usuario: string }[];
  motivo_destino: string | null;
  fecha_documento: string | null;
}

export interface RespuestaVerificacion {
  documento_id: string;
  verificaciones: { orden: number; usuario: string }[];
  requeridas: number;
  completa: boolean;
  estado: EstadoDocumento;
  pendientes: string[];
}

export interface OrdenPorAutorizar {
  documento_id: string;
  version: number;
  nivel_prioridad: NivelPrioridad | null;
  canal_origen: string;
  creado_en: string | null;
  cobertura: string | null;
  motivo_destino: string | null;
  documentacion_incompleta: boolean;
  procedimientos: string[];
  cups: string[];
  diagnosticos: string[];
  justificacion: string;
  fecha_documento: string | null;
}

export interface BandejaAutorizaciones {
  por_autorizar: OrdenPorAutorizar[];
  avisos_urgencias: OrdenPorAutorizar[];
}

export interface Autorizacion {
  estado: "aprobada" | "devuelta";
  usuario: string;
  motivo: string;
  fecha_hora: string;
}

export interface Resumen {
  total: number;
  por_estado: Record<string, number>;
  por_prioridad: Record<string, number>;
  en_revision: number;
  alertas_sin_acuse: number;
  recetas_por_verificar: number;
  ordenes_por_autorizar: number;
  enrutados: number;
  entregados_hoy: number;
}

/** Fase D: configuración (RN-L), métricas (RN-R) y administración (RN-K). */
export interface Rango {
  min: number;
  max: number;
  solo_a_la_baja: boolean;
  base: number;
  efectivo: number;
}

export interface HallazgoAmpliado {
  concepto: string;
  sinonimos: string[];
  cie10: string[];
  cie11: string[];
}

export interface Ampliaciones {
  alto_riesgo: string[];
  control_especial: string[];
  hallazgos_criticos: HallazgoAmpliado[];
}

export interface CambiosConfiguracion {
  umbrales: Record<string, number>;
  ampliaciones: Ampliaciones;
  /** RN-L1: conjunto completo de destinos sin uso desde esta versión. Ausente: la versión no los toca. */
  destinos_inactivos?: string[] | null;
}

export interface DestinoConfigurado {
  destino: string;
  activo: boolean;
  /** Emergencia y Revisión humana: nunca se desactivan (RN-L2). */
  protegido: boolean;
}

export interface FilaSimulacion {
  documento_id: string;
  version: number;
  tipo: string;
  estado_actual: string;
  estado_simulado: string;
  prioridad_actual: string;
  prioridad_simulada: string;
  motivo_actual: string | null;
  motivo_simulado: string | null;
  destino_actual: string;
  destino_simulado: string;
  cambia: boolean;
}

export interface Simulacion {
  documentos_evaluados: number;
  sin_propuesta: number;
  cambian: number;
  mas_a_revision: number;
  mas_automaticos: number;
  detalle: FilaSimulacion[];
}

export interface VersionConfiguracion {
  id: number | null;
  numero: number | null;
  autor: string;
  motivo: string;
  cambios: Partial<CambiosConfiguracion>;
  simulacion?: Simulacion | null;
  toca_seguridad?: boolean;
  aprobaciones?: { usuario: string; fecha_hora: string }[];
  aprobaciones_requeridas?: number;
  estado: string;
  creado_en?: string | null;
  vigente_desde: string | null;
  vigente_hasta?: string | null;
  cierre_por?: string | null;
  cierre_motivo?: string | null;
}

export interface Configuracion {
  vigente: VersionConfiguracion;
  umbrales_base: Record<string, unknown>;
  umbrales_efectivos: Record<string, unknown>;
  rangos: Record<string, Rango>;
  no_configurable: { news2: Record<string, number> };
  listas: {
    alto_riesgo: { base: string[]; ampliadas: string[] };
    control_especial: { base: string[]; ampliadas: string[] };
    hallazgos_criticos: { base: string[]; ampliados: string[] };
  };
  calidad: { limite_correccion_campo: number; simulacion_ultimos: number };
  destinos?: DestinoConfigurado[];
  propuestas: VersionConfiguracion[];
  historial: VersionConfiguracion[];
}

export interface AvisoMetrica {
  regla: string;
  campo: string;
  tasa: number;
  limite: number;
  umbral: string;
  umbral_actual: number;
  umbral_propuesto: number;
  propuesta: string;
}

export interface Metricas {
  periodo_dias: number;
  calculado_en: string;
  documentos: number;
  procesados: number;
  por_estado: Record<string, number>;
  por_prioridad: Record<string, number>;
  tasa_automatizacion: number | null;
  revision_por_motivo: Record<string, { n: number; porcentaje: number }>;
  tiempo_por_etapa_s: Record<string, number>;
  acuse_criticos: { emitidas: number; acusadas: number; pendientes: number; minutos_promedio: number | null; dentro_de_plazo: number; plazo_min: number };
  limite_correccion_campo: number;
  correccion_por_campo: { campo: string; correcciones: number; documentos_revisados: number; tasa: number; umbral_relacionado: string | null; supera_limite: boolean }[];
  avisos: AvisoMetrica[];
  falsos_negativos_criticos: { n: number; documentos: string[]; criticos_totales: number; tasa: number | null };
  versiones: Record<string, Record<string, number>>;
  tokens: { entrada: number; salida: number };
}

export interface UsuarioAdmin {
  usuario: string;
  nombre: string;
  rol: string;
  tipo: "persona" | "servicio";
  activo: boolean;
  creado_por: string;
  creado_en: string | null;
  desactivado_en: string | null;
  /** La cuenta tiene clave: inicia sesión y nadie firma en su nombre sin ella (RN-K5). */
  con_clave?: boolean;
}

/** Cuenta que inició sesión (RN-K5). */
export interface CuentaSesion {
  usuario: string;
  nombre: string;
  rol: string;
  /** La clave la puso otra persona: hay que cambiarla antes de seguir. */
  debe_cambiar_clave?: boolean;
}

export interface EstadoSesion {
  sesion: CuentaSesion | null;
  /** La instalación no tiene ninguna cuenta: toca crear el primer administrador (RN-S3). */
  sin_cuentas?: boolean;
  nombre_sede?: string;
}

/** Un rol tal como lo describe el backend (tabla K como datos, GET /auth/roles). */
export interface RolApi {
  id: string;
  nombre: string;
  descripcion: string;
  secciones: string[];
  acciones: string[];
  ve_documentos: boolean;
  ruta_inicial: string;
  modo_discreto: boolean;
  alto_contraste: boolean;
  pantalla_compartida: boolean;
}

export interface Acceso {
  documento_id: string;
  usuario: string;
  accion: string;
  fecha_hora: string;
}

export interface FichaPack {
  pais: string;
  nombre: string;
  version_pack: string;
  formato: Record<string, string>;
  terminologia: Record<string, string | null>;
  identidad_profesional: { registro: string; ambito: string; verificacion_en_linea: Record<string, unknown> };
  tipos_documento_paciente: Record<string, { nombre: string; estado: string; nacional: boolean; no_identificado: boolean }>;
  coberturas: Record<string, { modelo: string; entidad: string; estado: string }>;
  urgencias: Record<string, unknown>;
  retencion: { anios: number; archivo_gestion_anios: number | null; archivo_central_anios: number | null; norma: string | null; purga_automatica: boolean };
  datos_personales: Record<string, unknown>;
  listas: Record<string, number>;
  por_confirmar: string[];
}

export interface PuestaEnMarcha {
  listo: boolean;
  requisitos: { clave: string; requisito: string; cumplido: boolean; detalle: string }[];
}

// --- Directorio de pacientes (RN-M6) ----------------------------------------------------------------

/** Padrón de profesionales de la instalación (RN-A7, RN-CO5). */
export interface ProfesionalRegistrado {
  id: number;
  registro: string;
  nombre: string;
  profesion: string | null;
  tipo_documento: string | null;
  numero_documento: string | null;
  activo: boolean;
  creado_por: string;
  creado_en: string | null;
  registro_consultado_en: string | null;
  registro_consultado_por: string | null;
}

export interface PacienteFicha {
  id: number;
  pais: string;
  tipo_documento: string;
  numero_documento: string;
  nombre: string;
  edad: number | null;
  sexo: string | null;
  documentos: number;
  creado_en: string | null;
  actualizado_en: string | null;
}

export interface CorreccionDePaciente {
  fecha_hora: string;
  usuario: string;
  motivo: string;
  anterior: Record<string, unknown>;
  nuevo: Record<string, unknown>;
}

export interface DocumentoDePaciente {
  documento_id: string;
  version: number;
  estado: EstadoDocumento;
  nivel_prioridad: NivelPrioridad | null;
  tipo: string | null;
  fecha_documento: string | null;
  creado_en: string | null;
}

/** RN-M6: el titular pide que una persona revise una decisión automatizada sobre uno de sus documentos. */
export interface SolicitudTitular {
  id: number;
  paciente_id: number;
  paciente_nombre?: string;
  documento_id: string;
  version: number;
  presentada_por: "titular" | "representante";
  canal: "presencial" | "telefono" | "correo" | "escrito";
  motivo: string;
  registrada_por: string;
  registrada_en: string;
  vence_en: string;
  estado: "pendiente" | "respondida";
  resultado: "mantenida" | "corregida" | null;
  respuesta: string | null;
  respondida_por: string | null;
  respondida_en: string | null;
}

export interface PacienteDetalle extends PacienteFicha {
  historial: CorreccionDePaciente[];
  documentos_listado: DocumentoDePaciente[];
  solicitudes: SolicitudTitular[];
}

export interface ListadoPacientes {
  items: PacienteFicha[];
  total: number;
  limit: number;
  offset: number;
}
