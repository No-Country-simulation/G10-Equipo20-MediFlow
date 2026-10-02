import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { type Rol, type RolId, rolPorId } from "./roles";
import { useSesion } from "./sesion";

const CLAVE = "mediflow.rol";

interface ContextoRol {
  rol: Rol;
  cambiarRol: (id: RolId) => void;
  modoDiscreto: boolean;
  alternarModoDiscreto: () => void;
}

const Contexto = createContext<ContextoRol | null>(null);

/** `?rol=gestor` en la URL abre la aplicación con ese rol (enlaces de demostración); si no, el rol recordado en este navegador. */
function leerRolGuardado(): Rol {
  try {
    const enUrl = new URLSearchParams(window.location.search).get("rol");
    if (enUrl) return rolPorId(enUrl);
    return rolPorId(localStorage.getItem(CLAVE));
  } catch {
    return rolPorId(null);
  }
}

/**
 * Con sesión, el rol es el de la cuenta y no se cambia en pantalla (RN-K1). Sin sesión (demostración),
 * se elige en la barra lateral y se recuerda en este navegador.
 */
export function RolProvider({ children, rolInicial }: { children: ReactNode; rolInicial?: RolId }) {
  const { cuenta, versionRoles } = useSesion();
  const [elegido, setRol] = useState<Rol>(() => (rolInicial ? rolPorId(rolInicial) : leerRolGuardado()));
  const rolDeLaCuenta = cuenta?.rol ?? null;
  // Cuando el backend entrega los roles, el elegido se vuelve a buscar por su id para tomar la definición nueva.
  const rol = useMemo(() => rolPorId(rolDeLaCuenta ?? elegido.id), [rolDeLaCuenta, elegido, versionRoles]);
  const [discreto, setDiscreto] = useState<boolean>(rol.modoDiscreto);

  useEffect(() => {
    if (rolDeLaCuenta) setDiscreto(rolPorId(rolDeLaCuenta).modoDiscreto);
  }, [rolDeLaCuenta]);

  const valor = useMemo<ContextoRol>(
    () => ({
      rol,
      cambiarRol: (id) => {
        if (rolDeLaCuenta) return;
        const nuevo = rolPorId(id);
        setRol(nuevo);
        setDiscreto(nuevo.modoDiscreto);
        try {
          localStorage.setItem(CLAVE, nuevo.id);
        } catch {
          /* sin almacenamiento disponible */
        }
      },
      modoDiscreto: discreto,
      alternarModoDiscreto: () => setDiscreto((v) => !v),
    }),
    [rol, discreto, rolDeLaCuenta, versionRoles],  // eslint-disable-line react-hooks/exhaustive-deps
  );
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useRol(): ContextoRol {
  const ctx = useContext(Contexto);
  if (!ctx) throw new Error("useRol requiere RolProvider");
  return ctx;
}
