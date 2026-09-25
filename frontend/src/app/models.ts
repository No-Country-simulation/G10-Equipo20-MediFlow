export interface DocumentRecord {
  document_id: string;
  original_filename: string;
  format: string | null;
  size_bytes: number | null;
  received_at: string;
  country: string;
  status: string;
  processing_attempts: number;
  rejection_reason: string | null;
}
export interface Page {
  page: number;
  text: string;
  method: "embedded_text" | "gemini_ocr" | "human_corrected";
  engine: "pymupdf" | "gemini" | null;
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
  routing: { destination: string; delivery_status: string } | null;
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
export const TYPES = [
  "ECHOCARDIOGRAM_REPORT",
  "SPIROMETRY_REPORT",
  "CHEST_IMAGING_REPORT",
  "ECG_REPORT",
  "OTHER",
  "UNKNOWN",
];
export const SPECIALTIES = ["CARDIOLOGY", "PULMONOLOGY", "CARDIOPULMONARY", "OTHER", "UNKNOWN"];
export function label(value: string): string {
  return (
    (
      {
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
