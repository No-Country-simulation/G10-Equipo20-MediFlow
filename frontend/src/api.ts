/** Cliente de la API REST de MediFlow. Todas las rutas pasan por /api (proxy de Vite o nginx). */
import type {
  Acceso,
  AlertaListada,
  Autorizacion,
  BandejaAutorizaciones,
  CambiosConfiguracion,
  Configuracion,
  DatosArchivo,
  DocumentoDetalle,
  DocumentoRequest,
  FichaPack,
  ItemCola,
  Listado,
  Metricas,
  PuestaEnMarcha,
  RecetaPorVerificar,
  ResolucionRequest,
  RespuestaEntrega,
  RespuestaVerificacion,
  ResultadoTriaje,
  Resumen,
  Simulacion,
  UsuarioAdmin,
  VersionConfiguracion,
} from "./types";

export const BASE_URL = "/api";

export class ErrorApi extends Error {
  constructor(public status: number, public detalle: string, public cuerpo?: unknown) {
    super(detalle);
  }
}

/** RN-K3: cada acceso se atribuye al usuario que firma en este navegador (sin autenticación en el MVP). */
function usuarioActual(): string | null {
  try {
    return localStorage.getItem("mediflow.usuario");
  } catch {
    return null;
  }
}

async function llamar<T>(ruta: string, init?: RequestInit): Promise<T> {
  const cabeceras: Record<string, string> = { "Content-Type": "application/json" };
  const usuario = usuarioActual();
  if (usuario && usuario.trim()) cabeceras["X-Usuario"] = usuario.trim();
  const respuesta = await fetch(`${BASE_URL}${ruta}`, {
    ...init,
    headers: { ...cabeceras, ...((init?.headers as Record<string, string> | undefined) ?? {}) },
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

// --- Fase D: configuración (RN-L) ---------------------------------------------------------------

export function obtenerConfiguracion(): Promise<Configuracion> {
  return llamar<Configuracion>("/configuracion");
}

export function simularConfiguracion(cambios: CambiosConfiguracion, ultimos?: number): Promise<Simulacion> {
  return llamar("/configuracion/simular", { method: "POST", body: JSON.stringify({ cambios, ultimos }) });
}

export function proponerConfiguracion(cuerpo: { cambios: CambiosConfiguracion; usuario: string; rol: string; motivo: string }): Promise<VersionConfiguracion> {
  return llamar("/configuracion/propuestas", { method: "POST", body: JSON.stringify(cuerpo) });
}

export function aprobarConfiguracion(id: number, actor: { usuario: string; rol: string }): Promise<VersionConfiguracion> {
  return llamar(`/configuracion/propuestas/${id}/aprobar`, { method: "POST", body: JSON.stringify(actor) });
}

export function rechazarConfiguracion(id: number, cuerpo: { usuario: string; rol: string; motivo: string }): Promise<VersionConfiguracion> {
  return llamar(`/configuracion/propuestas/${id}/rechazar`, { method: "POST", body: JSON.stringify(cuerpo) });
}

// --- Fase D: métricas (RN-R) --------------------------------------------------------------------

export function obtenerMetricas(dias = 30): Promise<Metricas> {
  return llamar<Metricas>(`/metricas?dias=${dias}`);
}

// --- Fase D: administración (RN-K, RN-S3) --------------------------------------------------------

export function listarUsuarios(): Promise<UsuarioAdmin[]> {
  return llamar<UsuarioAdmin[]>("/administracion/usuarios");
}

export function crearUsuario(cuerpo: { usuario: string; nombre: string; rol: string; tipo: string; actor: string }): Promise<UsuarioAdmin> {
  return llamar("/administracion/usuarios", { method: "POST", body: JSON.stringify(cuerpo) });
}

export function cambiarEstadoUsuario(usuario: string, activo: boolean, actor: string): Promise<UsuarioAdmin> {
  return llamar(`/administracion/usuarios/${encodeURIComponent(usuario)}/${activo ? "activar" : "desactivar"}`, { method: "POST", body: JSON.stringify({ actor }) });
}

export function listarAccesos(documentoId?: string): Promise<Acceso[]> {
  const q = documentoId ? `?documento_id=${encodeURIComponent(documentoId)}` : "";
  return llamar<Acceso[]>(`/administracion/accesos${q}`);
}

export function obtenerPack(): Promise<FichaPack> {
  return llamar<FichaPack>("/administracion/pack");
}

export function puestaEnMarcha(): Promise<PuestaEnMarcha> {
  return llamar<PuestaEnMarcha>("/administracion/puesta_en_marcha");
}
