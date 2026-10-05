/** Plazos de la sección 7 del documento de reglas, en minutos. */
import type { EstadoDocumento, NivelPrioridad } from "../types";

export const PLAZO_ACUSE_MIN = 15; // RN-F2
export const PLAZO_COLA_MIN: Record<NivelPrioridad, number> = { "Crítico": 15, "Urgente": 120, "Rutina": 24 * 60 }; // RN-J2

export interface Plazo {
  minutosRestantes: number;
  vencido: boolean;
  /** Menos de un tercio del plazo, o menos de 5 minutos en críticos: pide atención. */
  apremia: boolean;
  texto: string;
}

export function formatearMinutos(minutos: number): string {
  const abs = Math.abs(Math.round(minutos));
  if (abs < 60) return `${abs} min`;
  if (abs < 48 * 60) {
    const h = Math.floor(abs / 60);
    const m = abs % 60;
    return m ? `${h} h ${m} min` : `${h} h`;
  }
  return `${Math.round(abs / 60 / 24)} d`;
}

export function calcularPlazo(desde: string | Date, plazoMinutos: number, ahora: Date = new Date()): Plazo {
  const inicio = typeof desde === "string" ? new Date(desde) : desde;
  const transcurrido = (ahora.getTime() - inicio.getTime()) / 60000;
  const restantes = plazoMinutos - transcurrido;
  const vencido = restantes <= 0;
  const apremia = !vencido && (restantes <= plazoMinutos / 3 || (plazoMinutos <= 15 && restantes <= 5));
  return {
    minutosRestantes: restantes,
    vencido,
    apremia,
    texto: vencido ? `vencido hace ${formatearMinutos(restantes)}` : `${formatearMinutos(restantes)} restantes`,
  };
}

/** Plazo de la cola de revisión para un documento, o null si no está en revisión (RN-J2). */
export function plazoDeRevision(estado: EstadoDocumento, nivel: NivelPrioridad | null, creadoEn: string | null, ahora?: Date): Plazo | null {
  if (estado !== "EN_REVISION_HUMANA" || !creadoEn) return null;
  return calcularPlazo(creadoEn, PLAZO_COLA_MIN[nivel ?? "Rutina"], ahora);
}
