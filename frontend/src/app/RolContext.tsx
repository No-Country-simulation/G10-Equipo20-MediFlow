import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import { type Rol, type RolId, rolPorId } from "./roles";

const CLAVE = "mediflow.rol";

interface ContextoRol {
  rol: Rol;
  cambiarRol: (id: RolId) => void;
  modoDiscreto: boolean;
  alternarModoDiscreto: () => void;
}

const Contexto = createContext<ContextoRol | null>(null);

function leerRolGuardado(): Rol {
  try {
    return rolPorId(localStorage.getItem(CLAVE));
  } catch {
    return rolPorId(null);
  }
}

/** El MVP no tiene autenticación (sección 2.1); el rol se elige en la barra lateral y se recuerda en este navegador. */
export function RolProvider({ children, rolInicial }: { children: ReactNode; rolInicial?: RolId }) {
  const [rol, setRol] = useState<Rol>(() => (rolInicial ? rolPorId(rolInicial) : leerRolGuardado()));
  const [discreto, setDiscreto] = useState<boolean>(rol.modoDiscreto);

  const valor = useMemo<ContextoRol>(
    () => ({
      rol,
      cambiarRol: (id) => {
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
    [rol, discreto],
  );
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useRol(): ContextoRol {
  const ctx = useContext(Contexto);
  if (!ctx) throw new Error("useRol requiere RolProvider");
  return ctx;
}
