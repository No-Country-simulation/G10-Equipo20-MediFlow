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
  ListadoPacientes,
  Metricas,
  PacienteDetalle,
  PacienteFicha,
  CorreccionDePaciente,
  CuentaSesion,
  PuestaEnMarcha,
  RecetaPorVerificar,
  ResolucionRequest,
  Revisor,
  RespuestaEntrega,
  RespuestaVerificacion,
  ResultadoTriaje,
  Resumen,
  Simulacion,
  SolicitudTitular,
  UsuarioAdmin,
  VersionConfiguracion,
RolApi, EstadoSesion } from "./types";

export const BASE_URL = "/api";
/** Se emite cuando una petición llega sin sesión válida, para que la interfaz vuelva a pedirla. */
export const EVENTO_SESION = "mediflow:sesion";

export class ErrorApi extends Error {
  constructor(public status: number, public detalle: string, public cuerpo?: unknown) {
    super(detalle);
  }
}

async function llamar<T>(ruta: string, init?: RequestInit): Promise<T> {
  // RN-K5, RN-K3: la cuenta de la sesión (cookie) es quien consulta y firma; no viaja ningún nombre.
  const cabeceras: Record<string, string> = { "Content-Type": "application/json" };
  const respuesta = await fetch(`${BASE_URL}${ruta}`, {
    ...init,
    headers: { ...cabeceras, ...((init?.headers as Record<string, string> | undefined) ?? {}) },
  });
  const cuerpo = await respuesta.json().catch(() => null);
  if (!respuesta.ok && respuesta.status !== 400) {
    const detalle = (cuerpo && (cuerpo.detail ?? cuerpo.codigo_error)) || respuesta.statusText;
    if (respuesta.status === 401 && detalle === "sesion_requerida") {
      window.dispatchEvent(new Event(EVENTO_SESION));
      throw new ErrorApi(401, "Tu sesión terminó. Inicia sesión de nuevo.", cuerpo);
    }
    throw new ErrorApi(respuesta.status, typeof detalle === "string" ? detalle : JSON.stringify(detalle), cuerpo);
  }
  return cuerpo as T;
}

// --- Sesión (RN-K5) ---------------------------------------------------------------------------------

export function estadoSesion(): Promise<EstadoSesion> {
  return llamar("/auth/estado");
}

/** RN-S3: la primera cuenta de la instalación, de administrador. Solo mientras no exista ninguna. */
export function crearPrimerAdministrador(usuario: string, nombre: string, clave: string): Promise<CuentaSesion> {
  return llamar<CuentaSesion>("/auth/primer_administrador", { method: "POST", body: JSON.stringify({ usuario, nombre, clave }) });
}

/** La propia clave, con la actual en mano. */
export function cambiarMiClave(claveActual: string, claveNueva: string): Promise<CuentaSesion> {
  return llamar<CuentaSesion>("/auth/clave", { method: "POST", body: JSON.stringify({ clave_actual: claveActual, clave_nueva: claveNueva }) });
}

/** Tabla K como datos: el menú y el comportamiento de cada rol salen del backend (RN-K1). */
export function listarRoles(): Promise<RolApi[]> {
  return llamar<RolApi[]>("/auth/roles");
}

export function iniciarSesion(usuario: string, clave: string): Promise<CuentaSesion> {
  return llamar<CuentaSesion>("/auth/ingresar", { method: "POST", body: JSON.stringify({ usuario, clave }) });
}

export async function cerrarSesion(): Promise<void> {
  await llamar("/auth/salir", { method: "POST" });
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

/** RN-J3: personas activas cuyo rol resuelve la revisión. */
export function listarRevisores(): Promise<Revisor[]> {
  return llamar<Revisor[]>("/revision/revisores");
}

export function resolverRevision(
  documentoId: string,
  cuerpo: ResolucionRequest,
): Promise<{ documento_id: string; estado: string; resultado: ResultadoTriaje }> {
  return llamar(`/revision/${encodeURIComponent(documentoId)}/resolver`, { method: "POST", body: JSON.stringify(cuerpo) });
}

/** RN-Q5: el acuse lo da la cuenta de la sesión; un "leído" automático no cuenta. */
export function acusarAlerta(documentoId: string): Promise<{ estado_acuse: string; acusado_por: string; estado: string }> {
  return llamar(`/alertas/${encodeURIComponent(documentoId)}/acuse`, { method: "POST" });
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
  if (datos.paginas_por_documento) form.append("paginas_por_documento", datos.paginas_por_documento);
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

export function verificarReceta(documentoId: string): Promise<RespuestaVerificacion> {
  return llamar(`/farmacia/${encodeURIComponent(documentoId)}/verificar`, { method: "POST" });
}

export function bandejaAutorizaciones(): Promise<BandejaAutorizaciones> {
  return llamar<BandejaAutorizaciones>("/autorizaciones");
}

export function resolverAutorizacion(
  documentoId: string,
  cuerpo: { accion: "aprobar" | "devolver"; motivo: string },
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

export function proponerConfiguracion(cuerpo: { cambios: CambiosConfiguracion; motivo: string }): Promise<VersionConfiguracion> {
  return llamar("/configuracion/propuestas", { method: "POST", body: JSON.stringify(cuerpo) });
}

export function aprobarConfiguracion(id: number): Promise<VersionConfiguracion> {
  return llamar(`/configuracion/propuestas/${id}/aprobar`, { method: "POST" });
}

export function rechazarConfiguracion(id: number, cuerpo: { motivo: string }): Promise<VersionConfiguracion> {
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

export function crearUsuario(cuerpo: { usuario: string; nombre: string; rol: string; tipo: string; clave?: string }): Promise<UsuarioAdmin> {
  return llamar("/administracion/usuarios", { method: "POST", body: JSON.stringify(cuerpo) });
}

export function cambiarEstadoUsuario(usuario: string, activo: boolean): Promise<UsuarioAdmin> {
  return llamar(`/administracion/usuarios/${encodeURIComponent(usuario)}/${activo ? "activar" : "desactivar"}`, { method: "POST" });
}

export function definirClave(usuario: string, clave: string): Promise<UsuarioAdmin> {
  return llamar(`/administracion/usuarios/${encodeURIComponent(usuario)}/clave`, { method: "POST", body: JSON.stringify({ clave }) });
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

// --- Directorio de pacientes (RN-M6) ----------------------------------------------------------------

export function listarPacientes(filtros: { q?: string; limit?: number; offset?: number } = {}): Promise<ListadoPacientes> {
  const params = new URLSearchParams();
  for (const [clave, valor] of Object.entries(filtros)) {
    if (valor !== undefined && valor !== "") params.set(clave, String(valor));
  }
  const consulta = params.toString();
  return llamar<ListadoPacientes>(`/pacientes${consulta ? `?${consulta}` : ""}`);
}

export function obtenerPaciente(id: number): Promise<PacienteDetalle> {
  return llamar<PacienteDetalle>(`/pacientes/${id}`);
}

export function editarPaciente(
  id: number,
  cuerpo: { nombre?: string; edad?: number | null; motivo: string },
): Promise<PacienteFicha & { historial: CorreccionDePaciente[] }> {
  return llamar(`/pacientes/${id}`, { method: "PATCH", body: JSON.stringify(cuerpo) });
}

// --- Solicitudes del titular (RN-M6) -------------------------------------------------------------------

export function listarSolicitudesTitular(estado: "pendiente" | "respondida" | "todas" = "pendiente"): Promise<SolicitudTitular[]> {
  return llamar<SolicitudTitular[]>(`/pacientes/solicitudes?estado=${estado}`);
}

export function registrarSolicitudTitular(
  pacienteId: number,
  cuerpo: { documento_id: string; presentada_por: SolicitudTitular["presentada_por"]; canal: SolicitudTitular["canal"]; motivo: string },
): Promise<SolicitudTitular> {
  return llamar(`/pacientes/${pacienteId}/solicitudes`, { method: "POST", body: JSON.stringify(cuerpo) });
}

export function responderSolicitudTitular(
  id: number,
  cuerpo: { resultado: "mantenida" | "corregida"; respuesta: string },
): Promise<SolicitudTitular> {
  return llamar(`/pacientes/solicitudes/${id}/responder`, { method: "POST", body: JSON.stringify(cuerpo) });
}
