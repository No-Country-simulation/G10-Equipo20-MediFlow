import { claseEstado, ETIQUETA_ESTADO } from "../app/mensajes";
import type { Plazo } from "../app/plazos";
import type { EstadoDocumento, NivelPrioridad } from "../types";

/** Prioridad con icono, texto y color: nunca solo color (accesibilidad). */
export function TagPrioridad({ nivel }: { nivel: NivelPrioridad | null | undefined }) {
  if (nivel === "Crítico") return <span className="tag critico"><i aria-hidden="true">●</i>Crítico</span>;
  if (nivel === "Urgente") return <span className="tag urgente"><i aria-hidden="true">▲</i>Urgente</span>;
  if (nivel === "Rutina") return <span className="tag rutina">Rutina</span>;
  return <span className="tag neutro">Sin prioridad</span>;
}

export function TagEstado({ estado }: { estado: EstadoDocumento }) {
  return <span className={`tag ${claseEstado(estado)}`}>{ETIQUETA_ESTADO[estado] ?? estado}</span>;
}

export function ChipPlazo({ plazo }: { plazo: Plazo | null }) {
  if (!plazo) return <span className="muted">—</span>;
  const clase = plazo.vencido ? "vencido" : plazo.apremia ? "apremia" : "";
  return <span className={`plazo ${clase}`}>{plazo.texto}</span>;
}
