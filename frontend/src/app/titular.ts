import type { SolicitudTitular } from "../types";

/** RN-M6: textos de la solicitud del titular, iguales en la ficha, en el directorio y en el documento. */
export const PRESENTADA_POR: Record<SolicitudTitular["presentada_por"], string> = { titular: "el titular", representante: "su representante" };
export const CANAL: Record<SolicitudTitular["canal"], string> = { presencial: "presencial", telefono: "por teléfono", correo: "por correo", escrito: "por escrito" };
export const RESULTADO: Record<NonNullable<SolicitudTitular["resultado"]>, string> = { mantenida: "Decisión mantenida", corregida: "Decisión corregida" };

export function fechaCorta(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString("es-CO", { dateStyle: "medium" }) : "—";
}

export function vencida(s: SolicitudTitular, ahora: Date = new Date()): boolean {
  return s.estado === "pendiente" && new Date(s.vence_en).getTime() < ahora.getTime();
}
