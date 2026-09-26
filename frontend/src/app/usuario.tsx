import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

const CLAVE = "mediflow.usuario";

type Estado = [string, (u: string) => void];

const Contexto = createContext<Estado | null>(null);

function leerGuardado(): string {
  try {
    return localStorage.getItem(CLAVE) ?? "";
  } catch {
    return "";
  }
}

function guardar(u: string) {
  try {
    localStorage.setItem(CLAVE, u);
  } catch {
    /* sin almacenamiento disponible */
  }
}

/**
 * Usuario que firma acciones (RN-G4, RN-Q5) y al que se atribuyen los accesos (RN-K3).
 * Sin autenticación en el MVP: se escribe una sola vez en la barra lateral ("Firmo como") y se recuerda en este navegador.
 */
export function UsuarioProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuarioEstado] = useState<string>(leerGuardado);
  const valor = useMemo<Estado>(() => [usuario, (u) => { setUsuarioEstado(u); guardar(u); }], [usuario]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useUsuario(): Estado {
  const contexto = useContext(Contexto);
  // Fuera del proveedor (pantallas del modo demostración) cada componente recuerda el suyo.
  const [local, setLocal] = useState<string>(leerGuardado);
  if (contexto) return contexto;
  return [local, (u) => { setLocal(u); guardar(u); }];
}

export function enmascarar(valor: string | null | undefined): string {
  if (!valor) return "—";
  return valor
    .split(/\s+/)
    .map((p) => (p.length <= 1 ? p : p[0] + "▮".repeat(Math.min(6, p.length - 1))))
    .join(" ");
}
