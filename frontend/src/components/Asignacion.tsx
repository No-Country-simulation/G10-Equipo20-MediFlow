import { ArrowUpRight, UserRound } from "lucide-react";

import { rolPorId } from "../app/roles";

/** RN-J3: quién tiene el caso; RN-J2: a qué rol escaló. Texto e icono, nunca solo color. */
export function TagsAsignacion({ asignadoA, escaladoARol }: { asignadoA?: string | null; escaladoARol?: string | null }) {
  if (!asignadoA && !escaladoARol) return null;
  return (
    <>
      {escaladoARol && <span className="tag urgente" title="Escalado al siguiente rol de la cola"><ArrowUpRight size={13} aria-hidden="true" />Escalado a {rolPorId(escaladoARol).nombre}</span>}
      {asignadoA && <span className="tag marca" title="Revisor que tiene el caso"><UserRound size={13} aria-hidden="true" />Asignado a {asignadoA}</span>}
    </>
  );
}
