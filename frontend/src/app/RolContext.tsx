import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { type Rol, rolPorId } from "./roles";
import { useSesion } from "./sesion";

interface ContextoRol {
  rol: Rol;
  modoDiscreto: boolean;
  alternarModoDiscreto: () => void;
}

const Contexto = createContext<ContextoRol | null>(null);

/** El rol es el de la cuenta de la sesión y no se elige en pantalla (RN-K1). */
export function RolProvider({ children }: { children: ReactNode }) {
  const { cuenta, versionRoles } = useSesion();
  const rolDeLaCuenta = cuenta?.rol ?? null;
  // Cuando el backend entrega los roles, el de la cuenta se vuelve a buscar por su id para tomar la definición nueva.
  const rol = useMemo(() => rolPorId(rolDeLaCuenta), [rolDeLaCuenta, versionRoles]);
  const [discreto, setDiscreto] = useState<boolean>(rol.modoDiscreto);

  useEffect(() => { setDiscreto(rolPorId(rolDeLaCuenta).modoDiscreto); }, [rolDeLaCuenta]);

  const valor = useMemo<ContextoRol>(
    () => ({ rol, modoDiscreto: discreto, alternarModoDiscreto: () => setDiscreto((v) => !v) }),
    [rol, discreto],
  );
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useRol(): ContextoRol {
  const ctx = useContext(Contexto);
  if (!ctx) throw new Error("useRol requiere RolProvider");
  return ctx;
}
