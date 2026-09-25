import type { DocumentoDetalle, ItemCola, ResultadoTriaje } from "../types";

export function resultadoCaso1(cambios: Partial<ResultadoTriaje> = {}): ResultadoTriaje {
  return {
    documento_id: "DOC-CLIN-2026-8942",
    clasificacion: { tipo: "Informe de Imágenes", setting: "urgencia", especialidad: "Radiología", dominio: "Neumología", score_confianza: 0.97, nivel_prioridad: "Crítico" },
    extraccion: {
      paciente: { nome: "Carlos Eduardo Mendes", nombre: "Carlos Eduardo Mendes", edad: 52, sexo: "M", documento: { tipo: "ausente", valor: null, estado: "ausente" } },
      profesional: { nombre: "Andrés Felipe Rojas", registro_profesional: "RM 45678" },
      fecha_documento: "03/04/2026",
      signos_vitales: { FR: 28, SpO2: 88, FC: 118, PAS: 92, Temp: 37.1, NEWS2_total: 10 },
      diagnosticos: [{ texto: "Tromboembolismo pulmonar agudo", cie10_sugerido: "I26.9", cie11_sugerido: "BB00.0" }],
      procedimientos: [{ texto: "TC de tórax con contraste", cups: null }],
      medicamentos: [],
      hallazgos_criticos_detectados: ["TEP_AGUDO"],
    },
    evaluacion: { requiere_auditoria_humana: false, motivo_auditoria: null, campos_dudosos: [] },
    enrutamiento: {
      destino_principal: "Cola_Emergencia_Medica",
      destinos_secundarios: ["Historia_Clinica_Electronica"],
      justificacion_enrutamiento: "RN-E2: informe crítico a Emergencia + HCE",
      destinos_tras_revision: [],
      motivos_destino: {},
      entregas_retenidas: { Historia_Clinica_Electronica: "identidad_ausente_conciliar" },
      documentacion_incompleta: false,
    },
    notificacion_generada: {
      canal: "Slack", destinatario: "Jefe de Urgencias",
      mensaje: "Alerta Crítica. Doc: DOC-CLIN-2026-8942. Nivel: Crítico. Requiere acuse.",
      fecha_hora: "2026-09-25T10:00:00Z", enlace: "http://localhost:8000/documentos/DOC-CLIN-2026-8942", estado_acuse: "pendiente",
    },
    estado: "ENRUTADO",
    pack_pais: "CO",
    version_reglas: "8",
    historial_decisiones: [
      { regla: "RN-D2", evidencia: "TEP_AGUDO por codigo: cie10_sugerido I26.9", propuesta_llm: null, decision: "hallazgo_critico", fecha_hora: "2026-09-25T10:00:00Z" },
      { regla: "RN-E2", evidencia: "tipo=Informe de Imágenes nivel=Crítico", propuesta_llm: null, decision: "principal=Cola_Emergencia_Medica", fecha_hora: "2026-09-25T10:00:00Z" },
    ],
    status_backup: "ok",
    ruta_storage: "co/procesados/criticos/DOC-CLIN-2026-8942.json",
    posible_duplicado_de: null,
    ...cambios,
  };
}

export function detalleCaso1(cambios: Partial<DocumentoDetalle> = {}): DocumentoDetalle {
  return {
    documento_id: "DOC-CLIN-2026-8942",
    version: 1,
    estado: "ENRUTADO",
    nivel_prioridad: "Crítico",
    status_backup: "ok",
    ruta_storage: "co/procesados/criticos/DOC-CLIN-2026-8942.json",
    posible_duplicado_de: null,
    codigo_error: null,
    resultado: resultadoCaso1(),
    entregas: {},
    alerta: { nivel: "Crítico", canal: "Slack", destinatario: "Jefe de Urgencias", mensaje: "Alerta Crítica. Doc: DOC-CLIN-2026-8942. Nivel: Crítico. Requiere acuse.", estado_acuse: "pendiente", acusado_por: null, emitida_en: "2026-09-25T10:00:00Z" },
    correcciones: [],
    transiciones: [
      { de_estado: null, a_estado: "RECIBIDO", actor: "sistema", motivo: "documento recibido", fecha_hora: "2026-09-25T10:00:00Z" },
      { de_estado: "RECIBIDO", a_estado: "VALIDADO", actor: "sistema", motivo: "formato, tamaño, id y duplicados verificados", fecha_hora: "2026-09-25T10:00:01Z" },
      { de_estado: "VALIDADO", a_estado: "CLASIFICADO", actor: "sistema", motivo: "LLM: Informe de Imágenes, score 0.97", fecha_hora: "2026-09-25T10:00:02Z" },
      { de_estado: "CLASIFICADO", a_estado: "EXTRAIDO", actor: "sistema", motivo: "datos clínicos estructurados", fecha_hora: "2026-09-25T10:00:03Z" },
      { de_estado: "EXTRAIDO", a_estado: "EVALUADO", actor: "sistema", motivo: "prioridad Crítico", fecha_hora: "2026-09-25T10:00:04Z" },
      { de_estado: "EVALUADO", a_estado: "ENRUTADO", actor: "sistema", motivo: "RN-E2", fecha_hora: "2026-09-25T10:00:05Z" },
    ],
    ...cambios,
  };
}

export const COLA: ItemCola[] = [
  { documento_id: "DOC-CRIT", version: 1, nivel_prioridad: "Crítico", motivo_auditoria: "critico_baja_confianza", campos_dudosos: ["diagnostico_codigo"], tipo: "Informe de Imágenes", creado_en: "2026-09-25T10:05:00Z", plazo_minutos: 15 },
  { documento_id: "DOC-RUT-1", version: 1, nivel_prioridad: "Rutina", motivo_auditoria: "clasificacion_baja_confianza", campos_dudosos: ["clasificacion.tipo"], tipo: "Informe de Laboratorio", creado_en: "2026-09-25T10:00:00Z", plazo_minutos: 1440 },
];
