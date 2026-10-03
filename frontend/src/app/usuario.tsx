import { useSesion } from "./sesion";

type Estado = [string, (u: string) => void];

/** Quien firma acciones (RN-G4, RN-Q5) y a quien se atribuyen los accesos (RN-K3): siempre la cuenta de la sesión (RN-K5). */
export function useUsuario(): Estado {
  const { cuenta } = useSesion();
  return [cuenta?.usuario ?? "", () => undefined];
}

export function enmascarar(valor: string | null | undefined): string {
  if (!valor) return "—";
  return valor
    .split(/\s+/)
    .map((p) => (p.length <= 1 ? p : p[0] + "▮".repeat(Math.min(6, p.length - 1))))
    .join(" ");
}
