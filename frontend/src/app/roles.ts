/** Roles de la tabla K del documento de reglas. Cada rol ve solo lo que necesita (RN-K1). */

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
  /** Roles que no ven datos clínicos (RN-K2). */
  veDocumentos: boolean;
  /** Modo discreto activo por defecto: pensado para pantallas compartidas de urgencias. */
  modoDiscreto: boolean;
}

const INICIO: ItemNavegacion = { ruta: "/inicio", etiqueta: "Inicio" };
const DOCUMENTOS: ItemNavegacion = { ruta: "/documentos", etiqueta: "Documentos" };
const REVISION: ItemNavegacion = { ruta: "/revision", etiqueta: "Cola de revisión", contador: "revision" };
const ALERTAS: ItemNavegacion = { ruta: "/alertas", etiqueta: "Alertas críticas", contador: "alertas" };
const FARMACIA: ItemNavegacion = { ruta: "/farmacia", etiqueta: "Farmacia" };
const AUTORIZACIONES: ItemNavegacion = { ruta: "/autorizaciones", etiqueta: "Autorizaciones" };
const ENTREGAS: ItemNavegacion = { ruta: "/entregas", etiqueta: "Entregas" };
const CONFIGURACION: ItemNavegacion = { ruta: "/configuracion", etiqueta: "Configuración" };
const METRICAS: ItemNavegacion = { ruta: "/metricas", etiqueta: "Métricas" };
const ADMINISTRACION: ItemNavegacion = { ruta: "/administracion", etiqueta: "Administración" };

export const ROLES: Rol[] = [
  {
    id: "auditor_clinico",
    nombre: "Auditor clínico",
    descripcion: "Resuelve la cola de revisión humana; puede bajar una prioridad con justificación escrita.",
    rutaInicial: "/revision",
    navegacion: [INICIO, DOCUMENTOS, REVISION, ALERTAS, ENTREGAS],
    veDocumentos: true,
    modoDiscreto: false,
  },
  {
    id: "quimico_farmaceutico",
    nombre: "Químico farmacéutico",
    descripcion: "Verifica recetas; las de alto riesgo y control especial llevan doble verificación.",
    rutaInicial: "/farmacia",
    navegacion: [INICIO, FARMACIA, DOCUMENTOS],
    veDocumentos: true,
    modoDiscreto: false,
  },
  {
    id: "auditor_autorizaciones",
    nombre: "Auditor de autorizaciones",
    descripcion: "Aprueba o devuelve órdenes ambulatorias con su documentación mínima.",
    rutaInicial: "/autorizaciones",
    navegacion: [INICIO, AUTORIZACIONES, DOCUMENTOS],
    veDocumentos: true,
    modoDiscreto: false,
  },
  {
    id: "jefe_urgencias",
    nombre: "Jefe de urgencias",
    descripcion: "Da acuse a las alertas críticas y las reasigna.",
    rutaInicial: "/alertas",
    navegacion: [INICIO, ALERTAS, DOCUMENTOS],
    veDocumentos: true,
    modoDiscreto: true,
  },
  {
    id: "gestor",
    nombre: "Gestor de la clínica",
    descripcion: "Configuración dentro de límites y métricas. No revisa documentos.",
    rutaInicial: "/metricas",
    navegacion: [INICIO, METRICAS, CONFIGURACION],
    veDocumentos: false,
    modoDiscreto: true,
  },
  {
    id: "administrador",
    nombre: "Administrador del sistema",
    descripcion: "Usuarios y pack de país. Nada clínico.",
    rutaInicial: "/administracion",
    navegacion: [INICIO, ADMINISTRACION],
    veDocumentos: false,
    modoDiscreto: true,
  },
];

export const ROL_POR_DEFECTO: RolId = "auditor_clinico";

export function rolPorId(id: string | null | undefined): Rol {
  return ROLES.find((r) => r.id === id) ?? ROLES.find((r) => r.id === ROL_POR_DEFECTO)!;
}

export function rolPuedeVer(rol: Rol, ruta: string): boolean {
  if (ruta === "/demo") return true;
  if (ruta.startsWith("/documentos/")) return rol.veDocumentos;
  return rol.navegacion.some((item) => ruta === item.ruta || ruta.startsWith(item.ruta + "/"));
}
