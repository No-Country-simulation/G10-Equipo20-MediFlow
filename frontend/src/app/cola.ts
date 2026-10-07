/** Cola persistente de procesamiento (RN-P2). En modo worker la API responde 202 con el original guardado y un
 * worker aparte corre el triaje; mientras tanto la pantalla pregunta por el documento hasta que haya resultado. */
import type { DocumentoDetalle, EstadoDocumento } from "../types";

const EN_MANOS_DEL_WORKER: EstadoDocumento[] = ["RECIBIDO", "VALIDADO", "CLASIFICADO", "EXTRAIDO", "EVALUADO"];
export const INTERVALO_SONDEO_MS = 2000;

/** El documento sigue en manos del worker: todavía no hay nada que decidir. */
export function enProceso(d: DocumentoDetalle | null | undefined): boolean {
  if (!d?.trabajo) return false;
  return (d.trabajo.estado === "EN_COLA" || d.trabajo.estado === "EN_CURSO") && EN_MANOS_DEL_WORKER.includes(d.estado);
}

export function textoTrabajo(d: DocumentoDetalle): string {
  const t = d.trabajo;
  if (!t) return "";
  if (t.estado === "EN_COLA") return t.intento === 0 ? "En cola: un worker lo tomará en segundos." : `En cola para el intento ${t.intento + 1}: el motor falló y se reintenta solo.`;
  if (t.estado === "EN_CURSO") return `Procesando (intento ${t.intento})…`;
  if (t.estado === "FALLIDO") return "El motor no pudo leerlo tras varios intentos: pasó a revisión humana por fallo técnico.";
  return "Procesado.";
}
