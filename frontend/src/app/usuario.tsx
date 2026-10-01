import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { useRol } from "./RolContext";
import { useSesion } from "./sesion";

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
 * Con sesión firma la cuenta (RN-K5) y no se puede escribir otro nombre. Sin sesión se escribe en la barra lateral
 * ("Firmo como") y se recuerda en este navegador, salvo en una pantalla compartida: ahí la firma vive solo en memoria,
 * para que nadie firme con el nombre del anterior.
 */
export function UsuarioProvider({ children }: { children: ReactNode }) {
  const { rol } = useRol();
  const { cuenta } = useSesion();
  const compartida = rol.pantallaCompartida;
  const [usuario, setUsuarioEstado] = useState<string>(() => (compartida ? "" : leerGuardado()));

  useEffect(() => {
    setUsuarioEstado(compartida ? "" : leerGuardado());
  }, [compartida]);

  const valor = useMemo<Estado>(() => (cuenta ? [cuenta.usuario, () => undefined] : [usuario, (u) => {
    setUsuarioEstado(u);
    if (!compartida) guardar(u);
  }]), [usuario, compartida, cuenta]);
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
