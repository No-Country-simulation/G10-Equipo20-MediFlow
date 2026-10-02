/**
 * Roles de la tabla K del documento de reglas. Cada rol ve solo lo que necesita (RN-K1).
 *
 * La fuente de verdad es la tabla `roles` del backend (GET /auth/roles): qué secciones ve cada rol, qué puede
 * firmar y cómo se comporta su pantalla. Aquí solo vive lo que es de la interfaz: a qué ruta, etiqueta y contador
 * corresponde cada sección. La lista base sirve de respaldo mientras la API no responde.
 */
import type { RolApi } from "../types";

export type RolId =
  | "auditor_clinico"
  | "quimico_farmaceutico"
  | "auditor_autorizaciones"
  | "jefe_urgencias"
  | "gestor"
  | "administrador";

export interface ItemNavegacion {
  ruta: string;
  etiqueta: string;
  /** Contador que la barra lateral muestra junto al ítem, si aplica. */
  contador?: "revision" | "alertas";
}

export interface Rol {
  id: RolId;
  nombre: string;
  descripcion: string;
  rutaInicial: string;
  navegacion: ItemNavegacion[];
  /** Acciones que la API deja firmar a este rol (tabla K). */
  acciones: string[];
  /** Roles que no ven datos clínicos (RN-K2). */
  veDocumentos: boolean;
  /** Modo discreto activo por defecto: pensado para pantallas compartidas de urgencias. */
  modoDiscreto: boolean;
  /** Alto contraste por defecto: pantallas de urgencias, vistas a distancia y con luz variable. */
  altoContraste: boolean;
  /** Pantalla que usan varias personas: la firma no se recuerda y se pide en el momento de cada acuse (RN-Q5). */
  pantallaCompartida: boolean;
}

/** Cada sección que el backend nombra, y cómo se muestra en el menú. */
export const SECCIONES: Record<string, ItemNavegacion> = {
  inicio: { ruta: "/inicio", etiqueta: "Inicio" },
  documentos: { ruta: "/documentos", etiqueta: "Documentos" },
  revision: { ruta: "/revision", etiqueta: "Cola de revisión", contador: "revision" },
  alertas: { ruta: "/alertas", etiqueta: "Alertas críticas", contador: "alertas" },
  farmacia: { ruta: "/farmacia", etiqueta: "Farmacia" },
  autorizaciones: { ruta: "/autorizaciones", etiqueta: "Autorizaciones" },
  entregas: { ruta: "/entregas", etiqueta: "Entregas" },
  pacientes: { ruta: "/pacientes", etiqueta: "Pacientes" },
  configuracion: { ruta: "/configuracion", etiqueta: "Configuración" },
  metricas: { ruta: "/metricas", etiqueta: "Métricas" },
  administracion: { ruta: "/administracion", etiqueta: "Administración" },
};

/** Convierte lo que dice el backend en un rol de la interfaz. Una sección desconocida se ignora, no rompe el menú. */
export function rolDesdeApi(r: RolApi): Rol {
  return {
    id: r.id as RolId,
    nombre: r.nombre,
    descripcion: r.descripcion,
    rutaInicial: r.ruta_inicial,
    navegacion: r.secciones.map((s) => SECCIONES[s]).filter((item): item is ItemNavegacion => Boolean(item)),
    acciones: r.acciones,
    veDocumentos: r.ve_documentos,
    modoDiscreto: r.modo_discreto,
    altoContraste: r.alto_contraste,
    pantallaCompartida: r.pantalla_compartida,
  };
}

/** Respaldo: la misma tabla K que siembra el backend, para arrancar sin servidor. */
const ROLES_BASE: RolApi[] = [
  { id: "auditor_clinico", nombre: "Auditor clínico", descripcion: "Resuelve la cola de revisión humana; puede bajar una prioridad con justificación escrita.",
    secciones: ["inicio", "documentos", "revision", "alertas", "pacientes", "entregas"], acciones: ["resolver_revision", "acusar_alerta", "editar_paciente"],
    ve_documentos: true, ruta_inicial: "/revision", modo_discreto: false, alto_contraste: false, pantalla_compartida: false },
  { id: "quimico_farmaceutico", nombre: "Químico farmacéutico", descripcion: "Verifica recetas; las de alto riesgo y control especial llevan doble verificación.",
    secciones: ["inicio", "farmacia", "documentos"], acciones: ["verificar_receta"],
    ve_documentos: true, ruta_inicial: "/farmacia", modo_discreto: false, alto_contraste: false, pantalla_compartida: false },
  { id: "auditor_autorizaciones", nombre: "Auditor de autorizaciones", descripcion: "Aprueba o devuelve órdenes ambulatorias con su documentación mínima.",
    secciones: ["inicio", "autorizaciones", "documentos"], acciones: ["resolver_autorizacion"],
    ve_documentos: true, ruta_inicial: "/autorizaciones", modo_discreto: false, alto_contraste: false, pantalla_compartida: false },
  { id: "jefe_urgencias", nombre: "Jefe de urgencias", descripcion: "Da acuse a las alertas críticas y las reasigna.",
    secciones: ["inicio", "alertas", "documentos"], acciones: ["acusar_alerta", "resolver_revision"],
    ve_documentos: true, ruta_inicial: "/alertas", modo_discreto: true, alto_contraste: true, pantalla_compartida: true },
  { id: "gestor", nombre: "Gestor de la clínica", descripcion: "Configuración dentro de límites y métricas. No revisa documentos.",
    secciones: ["inicio", "metricas", "configuracion"], acciones: ["configurar"],
    ve_documentos: false, ruta_inicial: "/metricas", modo_discreto: true, alto_contraste: false, pantalla_compartida: false },
  { id: "administrador", nombre: "Administrador del sistema", descripcion: "Usuarios y pack de país. Nada clínico.",
    secciones: ["inicio", "administracion"], acciones: ["administrar"],
    ve_documentos: false, ruta_inicial: "/administracion", modo_discreto: true, alto_contraste: false, pantalla_compartida: false },
];

/** Lista viva de roles: arranca con el respaldo y se reemplaza con lo que diga el backend. */
export const ROLES: Rol[] = ROLES_BASE.map(rolDesdeApi);

/** Reemplaza la lista con los roles del backend. Devuelve cuántos quedaron. */
export function registrarRoles(desdeApi: RolApi[]): number {
  if (!Array.isArray(desdeApi) || desdeApi.length === 0) return ROLES.length;
  ROLES.splice(0, ROLES.length, ...desdeApi.map(rolDesdeApi));
  return ROLES.length;
}

/** Vuelve al respaldo de la interfaz (pruebas: cada una arranca sin roles del backend). */
export function restaurarRolesBase(): void {
  ROLES.splice(0, ROLES.length, ...ROLES_BASE.map(rolDesdeApi));
}

export const ROL_POR_DEFECTO: RolId = "auditor_clinico";

export function rolPorId(id: string | null | undefined): Rol {
  return ROLES.find((r) => r.id === id) ?? ROLES.find((r) => r.id === ROL_POR_DEFECTO) ?? ROLES[0];
}

export function rolPuedeVer(rol: Rol, ruta: string): boolean {
  if (ruta === "/demo") return true;
  if (ruta.startsWith("/documentos/")) return rol.veDocumentos;
  return rol.navegacion.some((item) => ruta === item.ruta || ruta.startsWith(item.ruta + "/"));
}
