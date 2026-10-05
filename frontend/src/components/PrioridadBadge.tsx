import type { NivelPrioridad } from "../types";

const CLASE: Record<NivelPrioridad, string> = {
  "Crítico": "prioridad-critico",
  "Urgente": "prioridad-urgente",
  "Rutina": "prioridad-rutina",
};

export function PrioridadBadge({ nivel }: { nivel: NivelPrioridad | null | undefined }) {
  if (!nivel) return <span className="badge prioridad-sin">Sin prioridad</span>;
  return <span className={`badge ${CLASE[nivel]}`}>{nivel}</span>;
}
