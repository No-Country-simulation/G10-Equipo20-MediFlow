import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Estado vacío con icono, título y, si aplica, la acción que lo resuelve. */
export function Vacio({ icono: Icono, titulo, texto, accion }: { icono: LucideIcon; titulo: string; texto?: string; accion?: ReactNode }) {
  return (
    <div className="vacio">
      <Icono size={28} aria-hidden="true" />
      <strong>{titulo}</strong>
      {texto && <p className="muted">{texto}</p>}
      {accion}
    </div>
  );
}
