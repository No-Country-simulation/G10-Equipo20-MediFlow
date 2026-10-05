import { AlarmClock, OctagonAlert, TriangleAlert } from "lucide-react";

import { claseEstado, ETIQUETA_ESTADO } from "../app/mensajes";
import type { Plazo } from "../app/plazos";
import type { EstadoDocumento, NivelPrioridad } from "../types";

/**
 * Prioridad con icono, texto y color, nunca solo color. Sigue la norma de alarmas médicas IEC 60601-1-8:
 * rojo sólido para lo que exige respuesta inmediata, amarillo para lo que exige respuesta pronta.
 * Crítico y Urgente se separan también por luminosidad y por forma del icono.
 */
export function TagPrioridad({ nivel }: { nivel: NivelPrioridad | null | undefined }) {
  if (nivel === "Crítico") return <span className="tag critico fuerte"><OctagonAlert size={13} aria-hidden="true" />Crítico</span>;
  if (nivel === "Urgente") return <span className="tag urgente"><TriangleAlert size={13} aria-hidden="true" />Urgente</span>;
  if (nivel === "Rutina") return <span className="tag rutina">Rutina</span>;
  return <span className="tag neutro">Sin prioridad</span>;
}

export function TagEstado({ estado }: { estado: EstadoDocumento }) {
  return <span className={`tag ${claseEstado(estado)}`}>{ETIQUETA_ESTADO[estado] ?? estado}</span>;
}

export function ChipPlazo({ plazo }: { plazo: Plazo | null }) {
  if (!plazo) return <span className="muted">—</span>;
  const clase = plazo.vencido ? "vencido" : plazo.apremia ? "apremia" : "";
  return <span className={`plazo ${clase}`}>{plazo.vencido && <AlarmClock size={14} aria-hidden="true" />}{plazo.texto}</span>;
}
