import { useEffect, useState } from "react";

import { colaRevision } from "../api";
import type { ItemCola } from "../types";

/** Desde cuántos casos por fallo técnico se trata como una caída del motor y no como casos sueltos (RN-P2). */
export const UMBRAL_SISTEMA_DEGRADADO = 3;

export interface EstadoMotor {
  /** Hay tantos documentos por fallo técnico que el motor de extracción se considera caído. */
  degradado: boolean;
  /** Documentos que esperan transcripción humana por fallo técnico. */
  enEspera: number;
  /** De esos, cuántos son críticos. */
  criticos: number;
  /** Cuándo entró el primero: desde cuándo dura la caída. */
  desde: string | null;
}

/** Resume la cola de revisión en el estado del motor, con el mismo criterio para todas las pantallas. */
export function resumirFalloTecnico(cola: ItemCola[]): EstadoMotor {
  const porFallo = cola.filter((c) => c.motivo_auditoria === "fallo_tecnico");
  return {
    degradado: porFallo.length >= UMBRAL_SISTEMA_DEGRADADO,
    enEspera: porFallo.length,
    criticos: porFallo.filter((c) => c.nivel_prioridad === "Crítico").length,
    desde: porFallo.reduce<string | null>((min, c) => (min === null || c.creado_en < min ? c.creado_en : min), null),
  };
}

/**
 * Estado del motor para las bandejas que no ven la cola de revisión (Farmacia, Autorizaciones):
 * lo que la caída retiene sin leer también les falta a ellas. Sin conexión no se afirma nada.
 */
export function useEstadoMotor(): EstadoMotor | null {
  const [estado, setEstado] = useState<EstadoMotor | null>(null);
  useEffect(() => {
    let activo = true;
    colaRevision().then((cola) => activo && setEstado(resumirFalloTecnico(cola))).catch(() => activo && setEstado(null));
    return () => { activo = false; };
  }, []);
  return estado;
}
