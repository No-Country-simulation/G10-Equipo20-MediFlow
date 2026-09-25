/** Cliente de la API REST de MediFlow. Todas las rutas pasan por /api (proxy de Vite o nginx). */
import type {
  DocumentoDetalle,
  DocumentoRequest,
  ItemCola,
  ResolucionRequest,
  RespuestaEntrega,
  ResultadoTriaje,
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
