/** Cliente de la API REST de MediFlow. Todas las rutas pasan por /api (proxy de Vite o nginx). */
import type {
  AlertaListada,
  Autorizacion,
  BandejaAutorizaciones,
  DatosArchivo,
  DocumentoDetalle,
  DocumentoRequest,
  ItemCola,
  Listado,
  RecetaPorVerificar,
  ResolucionRequest,
  RespuestaEntrega,
  RespuestaVerificacion,
  ResultadoTriaje,
  Resumen,
} from "./types";

export const BASE_URL = "/api";

export class ErrorApi extends Error {
  constructor(public status: number, public detalle: string, public cuerpo?: unknown) {
    super(detalle);
  }
}

async function llamar<T>(ruta: string, init?: RequestInit): Promise<T> {
  const respuesta = await fetch(`${BASE_URL}${ruta}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const cuerpo = await respuesta.json().catch(() => null);
  if (!respuesta.ok && respuesta.status !== 400) {
    const detalle = (cuerpo && (cuerpo.detail ?? cuerpo.codigo_error)) || respuesta.statusText;
    throw new ErrorApi(respuesta.status, typeof detalle === "string" ? detalle : JSON.stringify(detalle), cuerpo);
  }
  return cuerpo as T;
}

export function enviarDocumento(request: DocumentoRequest): Promise<DocumentoDetalle> {
  return llamar<DocumentoDetalle>("/documentos", { method: "POST", body: JSON.stringify(request) });
}

export function consultarDocumento(documentoId: string): Promise<DocumentoDetalle> {
  return llamar<DocumentoDetalle>(`/documentos/${encodeURIComponent(documentoId)}`);
}

export function colaRevision(): Promise<ItemCola[]> {
  return llamar<ItemCola[]>("/revision");
}

export function resolverRevision(
  documentoId: string,
  cuerpo: ResolucionRequest,
): Promise<{ documento_id: string; estado: string; resultado: ResultadoTriaje }> {
  return llamar(`/revision/${encodeURIComponent(documentoId)}/resolver`, { method: "POST", body: JSON.stringify(cuerpo) });
}

export function acusarAlerta(documentoId: string, usuario: string): Promise<{ estado_acuse: string; acusado_por: string; estado: string }> {
  if (!usuario.trim()) {
    // RN-Q5: el acuse lo da un usuario identificado; un "leído" automático no cuenta.
    return Promise.reject(new ErrorApi(422, "RN-Q5: el acuse exige un usuario identificado"));
  }
  return llamar(`/alertas/${encodeURIComponent(documentoId)}/acuse`, { method: "POST", body: JSON.stringify({ usuario }) });
}

export function confirmarEntrega(documentoId: string, destino: string): Promise<RespuestaEntrega> {
  return llamar(`/documentos/${encodeURIComponent(documentoId)}/entregar`, { method: "POST", body: JSON.stringify({ destino }) });
}

/** Carga multipart de PDF, PNG o JPG. El backend valida el contenido real del archivo (RN-A1). */
export async function enviarArchivo(archivo: File, datos: DatosArchivo): Promise<DocumentoDetalle> {
  const form = new FormData();
  form.append("archivo", archivo, archivo.name);
  form.append("documento_id", datos.documento_id);
  form.append("canal_origen", datos.canal_origen);
  if (datos.cobertura_paciente) form.append("cobertura_paciente", datos.cobertura_paciente);
  if (datos.pais_origen) form.append("pais_origen", datos.pais_origen);
  const respuesta = await fetch(`${BASE_URL}/documentos/archivo`, { method: "POST", body: form });
  const cuerpo = await respuesta.json().catch(() => null);
  if (!respuesta.ok && respuesta.status !== 400) {
    const detalle = (cuerpo && cuerpo.detail) || respuesta.statusText;
    throw new ErrorApi(respuesta.status, typeof detalle === "string" ? detalle : JSON.stringify(detalle), cuerpo);
  }
  return cuerpo as DocumentoDetalle;
}

export function listarDocumentos(filtros: { estado?: string; nivel?: string; q?: string; limit?: number; offset?: number } = {}): Promise<Listado> {
  const params = new URLSearchParams();
  for (const [clave, valor] of Object.entries(filtros)) {
    if (valor !== undefined && valor !== "" && valor !== null) params.set(clave, String(valor));
  }
  const consulta = params.toString();
  return llamar<Listado>(`/documentos${consulta ? `?${consulta}` : ""}`);
}

export function urlOriginal(documentoId: string): string {
  return `${BASE_URL}/documentos/${encodeURIComponent(documentoId)}/original`;
}

export function urlVistaPrevia(documentoId: string, pagina = 1): string {
  return `${BASE_URL}/documentos/${encodeURIComponent(documentoId)}/vista_previa?pagina=${pagina}`;
}

export function listarAlertas(filtros: { estado_acuse?: string } = {}): Promise<AlertaListada[]> {
  const consulta = filtros.estado_acuse ? `?estado_acuse=${encodeURIComponent(filtros.estado_acuse)}` : "";
  return llamar<AlertaListada[]>(`/alertas${consulta}`);
}

export function colaFarmacia(): Promise<RecetaPorVerificar[]> {
  return llamar<RecetaPorVerificar[]>("/farmacia");
}

export function verificarReceta(documentoId: string, usuario: string): Promise<RespuestaVerificacion> {
  return llamar(`/farmacia/${encodeURIComponent(documentoId)}/verificar`, { method: "POST", body: JSON.stringify({ usuario }) });
}

export function bandejaAutorizaciones(): Promise<BandejaAutorizaciones> {
  return llamar<BandejaAutorizaciones>("/autorizaciones");
}

export function resolverAutorizacion(
  documentoId: string,
  cuerpo: { accion: "aprobar" | "devolver"; usuario: string; motivo: string },
): Promise<{ documento_id: string; autorizacion: Autorizacion; estado: string; pendientes: string[] }> {
  return llamar(`/autorizaciones/${encodeURIComponent(documentoId)}/resolver`, { method: "POST", body: JSON.stringify(cuerpo) });
}

export function obtenerResumen(): Promise<Resumen> {
  return llamar<Resumen>("/resumen");
}
