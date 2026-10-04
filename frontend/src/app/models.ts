export interface DocumentRecord {
  document_id: string;
  original_filename: string;
  format: string | null;
  size_bytes: number | null;
  received_at: string;
  country: string;
  status: string;
  priority?: string;
  processing_attempts: number;
  rejection_reason: string | null;
  patient_id: number | null;
  patient_match_status: string;
  patient_match_reason: string | null;
}
export interface Patient {
  id: number;
  country: string;
  identity_type: string;
  identity_number: string;
  name: string;
  age: number | null;
  document_count: number;
  created_at: string;
  updated_at: string;
}
export interface DestinationInput {
  code: string;
  name: string;
  kind: "DEPARTMENT" | "QUEUE" | "SYSTEM";
}
export interface Destination extends DestinationInput {
  active: boolean;
}
export interface RoutingRuleInput {
  document_type: string;
  specialty: string;
  destination_code: string;
  active: boolean;
}
export interface RoutingRule extends RoutingRuleInput {
  id: number;
}
export interface Page {
  page: number;
  text: string;
  method: "embedded_text" | "gemini_ocr" | "openai_ocr" | "human_corrected";
  engine: "pymupdf" | "gemini" | "openai" | null;
  uncertain: boolean;
}
export interface Evidence {
  page: number;
  quote: string;
}
export interface Classification {
  document_type: string;
  specialty: string;
  evidence: Evidence | null;
  reason: string;
}
export interface ExtractedField {
  name: string;
  value: string;
  unit: string | null;
  evidence: Evidence;
  entity_id?: string | null;
}
export interface DocumentCatalog {
  types: { code: string; name: string; fields: string[]; required_groups: string[][] }[];
  specialties: { code: string; name: string }[];
  rule_version: string;
}
export interface DocumentSummary {
  country: string;
  total: number;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  pending_review: number;
  delivered_local: number;
}
const catalogLabels: Record<string, string> = {};
export function registerCatalog(catalog: DocumentCatalog) {
  for (const item of [...catalog.types, ...catalog.specialties]) catalogLabels[item.code] = item.name;
}
export interface Result {
  document_id: string;
  status: string;
  content: { pages: Page[] } | null;
  classification: Classification | null;
  extraction: { fields: ExtractedField[] } | null;
  validation: {
    valid: boolean;
    requires_human_review: boolean;
    issues: string[];
  } | null;
  priority?: {
    level: "ROUTINE" | "URGENT" | "CRITICAL";
    source: "DEFAULT" | "EXPLICIT";
    evidence: Evidence | null;
    ambiguous: boolean;
  } | null;
  quality?: {
    score: number;
    threshold: number;
    components: {
      readability: number;
      completeness: number;
      evidence: number;
      consistency: number;
    };
    rule_version: string;
  } | null;
  local_alert?: {
    level: "URGENT" | "CRITICAL";
    message: string;
    evidence: Evidence;
    status: "REGISTERED_LOCAL";
  } | null;
  routing: { destination: string; delivery_status: string; external_delivery_status?: string } | null;
  patient?: { status: string; identity_type: string | null; identity_number: string | null;
              patient_id: number | null; reason: string | null } | null;
  error_code: string | null;
  processed_at: string;
  model: string;
}
export interface StateEvent {
  status: string;
  occurred_at: string;
  reason: string;
  attempt: number;
}
export interface ReviewAudit {
  action: string;
  reviewer: string;
  notes: string;
  reviewed_at: string;
  previous_result: Result;
}
export const STATUSES = [
  "RECIBIDO",
  "VALIDADO",
  "CLASIFICADO",
  "EXTRAIDO",
  "EVALUADO",
  "EN_REVISION_HUMANA",
  "RESUELTO",
  "ENRUTADO",
  "ENTREGADO",
  "RECHAZADO",
  "FALLO_TECNICO",
];
export function label(value: string): string {
  if (catalogLabels[value]) return catalogLabels[value];
  if (value.startsWith("MISSING_REQUIRED_FIELD:"))
    return "Falta campo obligatorio: " + label(value.split(":")[1]);
  return (
    (
      {
        UNASSESSED: "Sin evaluar",
        GENERAL_MEDICINE: "Medicina general",
        RADIOLOGY: "Radiología",
        PRESCRIPTION: "Receta médica",
        PROCEDURE_ORDER: "Orden de procedimiento",
        MEDICAL_CERTIFICATE: "Certificado médico",
        IMAGING_REPORT: "Informe de imágenes",
        test_name: "Prueba de laboratorio",
        test_result: "Resultado de laboratorio",
        reference_range: "Rango de referencia",
        medication_name: "Medicamento",
        medication_dose: "Dosis",
        medication_frequency: "Frecuencia",
        medication_route: "Vía de administración",
        medication_duration: "Duración",
        medication_concentration: "Concentración",
        requested_procedure: "Procedimiento solicitado",
        procedure_indication: "Indicación del procedimiento",
        certificate_purpose: "Finalidad del certificado",
        certificate_period: "Período del certificado",
        study_name: "Estudio",
        findings: "Hallazgos",
        conclusion: "Conclusión",
        ejection_fraction: "Fracción de eyección",
        fev1: "FEV1",
        rhythm: "Ritmo",
        REPEATED_ENTITIES_NOT_GROUPED: "Falta agrupar los medicamentos o pruebas repetidos",
        DISCHARGE_SUMMARY: "Epicrisis / informe de alta",
        LABORATORY_RESULT: "Resultados de laboratorio",
        LABORATORY_ORDER: "Orden de laboratorio",
        LABORATORY: "Laboratorio",
        LABORATORIO: "Laboratorio",
        HISTORIA_CLINICA: "Historia clínica",
        COLA_URGENCIAS_MEDICAS: "Cola de Urgencias Médicas",
        ROUTINE: "Rutina administrativa",
        URGENT: "Urgente declarado",
        CRITICAL: "Crítico declarado",
        PRIORITY_AMBIGUOUS: "Prioridad contradictoria o no reconocida: requiere revisión",
        LOW_DOCUMENT_QUALITY: "Calidad documental inferior al umbral configurado",
        HUMAN_REVIEW_REJECT: "Rechazado por revisión humana",
        patient_name: "Nombre del paciente",
        patient_age: "Edad del paciente",
        patient_identity: "Identificación del paciente",
        ordered_test: "Examen solicitado",
        ACCOUNT_ALREADY_EXISTS: "Ya existe una cuenta con ese email o identificación",
        ACCOUNT_DISABLED: "Esta cuenta está desactivada",
        DUPLICATE_OR_REFERENCED_RECORD: "El registro ya existe o está siendo utilizado",
        ROLE_IN_USE: "El rol está asignado a empleados. Reasígnalos antes de eliminarlo",
        ROLE_ALREADY_EXISTS: "Ya existe un rol con ese nombre",
        UNKNOWN_PERMISSION: "Selecciona permisos existentes",
        UPPERCASE_NAME_REQUIRED: "La clave debe estar en mayúsculas, con letras, números o guiones bajos",
        OPENAI_NOT_CONFIGURED: "Configura APIKEY_OPENAI en Variables de Configuración",
        GEMINI_NOT_CONFIGURED: "Configura APIKEY_GEMINI en Variables de Configuración",
        OPENAI_ACCESS_DENIED: "OpenAI rechazó la clave o su acceso al modelo",
        OPENAI_QUOTA_EXCEEDED: "Se alcanzó la cuota de OpenAI",
        OPENAI_TIMEOUT: "OpenAI superó el tiempo de espera. Puedes reintentar",
        OPENAI_REQUEST_FAILED: "OpenAI rechazó la solicitud. Comprueba el modelo y su configuración",
        OPENAI_INVALID_RESPONSE: "OpenAI devolvió un resultado inválido. Puedes reintentar",
        OPENAI_UNAVAILABLE: "OpenAI no está disponible. Puedes reintentar",
        OPENAI_INCOMPLETE_RESPONSE: "OpenAI devolvió una respuesta incompleta. Puedes reintentar",
        OPENAI_REFUSED: "OpenAI no pudo analizar este contenido",
        PATIENT_IDENTITY_NOT_FOUND: "No se encontró identificación del paciente",
        PATIENT_IDENTITY_INVALID_FORMAT: "La identificación no cumple el formato del país",
        PATIENT_IDENTITY_AMBIGUOUS: "Identificación o nombre ambiguo: requiere revisión",
        PATIENT_IDENTITY_CONFLICT: "La identificación coincide con otro nombre: requiere revisión",
        PATIENT_NAME_MISSING: "Se detectó una identificación, pero falta el nombre del paciente",
        LOCAL_INBOX_DELIVERED: "Disponible en la bandeja local del destino",
        professional_name: "Profesional firmante",
        document_date: "Fecha del documento",
        discharge_diagnosis: "Diagnóstico de egreso",
        discharge_treatment: "Tratamiento al alta",
        follow_up: "Control programado",
        OCR_UNCERTAIN: "Lectura incierta: contrasta el texto con el original",
        EMPTY_OR_UNREADABLE_PAGE: "Página vacía o ilegible",
        CLASSIFICATION_UNCERTAIN: "No se pudo determinar el tipo",
        OUTSIDE_INITIAL_SCOPE: "Documento fuera del alcance inicial",
        NO_EXTRACTED_FIELDS: "No hay campos extraídos",
        CLASSIFICATION_EVIDENCE_NOT_FOUND: "La evidencia del tipo no aparece en el texto",
        CLASSIFICATION_SPECIALTY_CONFLICT: "El tipo y la especialidad no coinciden",
        GEMINI_UNAVAILABLE: "El servicio de análisis no está disponible. Puedes reintentar.",
        GEMINI_QUOTA_EXCEEDED: "Se alcanzó la cuota del servicio de análisis.",
        GEMINI_TIMEOUT: "El análisis superó el tiempo de espera.",
        DOCUMENT_STORAGE_UNAVAILABLE: "No se pudo acceder al original. Intenta nuevamente.",
        RETRIES_EXHAUSTED: "Se agotaron los intentos de procesamiento",
        UPLOAD_RECEIVED: "Archivo recibido",
        FILE_VALIDATED: "Formato y contenido del archivo verificados",
        CLASSIFICATION_COMPLETED: "Clasificación finalizada",
        EXTRACTION_COMPLETED: "Extracción finalizada",
        VALIDATION_COMPLETED: "Evaluación documental finalizada",
        ROUTING_COMPLETED: "Destino local registrado",
        DOCUMENTARY_VALIDATION_ISSUES: "La evaluación requiere revisión",
        LOCAL_DESTINATION_REGISTERED: "Destino local registrado",
        RETRY_REQUESTED: "Reintento solicitado",
        HUMAN_REVIEW_APPROVE: "Lectura y datos aprobados",
        HUMAN_REVIEW_CORRECT: "Datos corregidos y verificados",
        MIGRATED_FROM_V1: "Estado conservado de la versión anterior",
        FILE_REJECTED: "Archivo rechazado durante la ingesta",
        RECIBIDO: "Recibido",
        VALIDADO: "Validado",
        CLASIFICADO: "Clasificado",
        EXTRAIDO: "Extraído",
        EVALUADO: "Evaluado",
        EN_REVISION_HUMANA: "Revisión humana",
        RESUELTO: "Resuelto",
        ENRUTADO: "Enrutado",
        ENTREGADO: "Entregado",
        RECHAZADO: "Rechazado",
        FALLO_TECNICO: "Fallo técnico",
        ECHOCARDIOGRAM_REPORT: "Ecocardiograma",
        SPIROMETRY_REPORT: "Espirometría",
        CHEST_IMAGING_REPORT: "Informe de tórax",
        ECG_REPORT: "Informe de ECG",
        OTHER: "Otro",
        UNKNOWN: "Sin determinar",
        CARDIOLOGY: "Cardiología",
        PULMONOLOGY: "Neumología",
        CARDIOPULMONARY: "Cardiopulmonar",
        CARDIOLOGIA: "Cardiología",
        NEUMOLOGIA: "Neumología",
        CARDIOPULMONAR: "Cardiopulmonar",
      } as Record<string, string>
    )[value] ?? value.replaceAll("_", " ")
  );
}
