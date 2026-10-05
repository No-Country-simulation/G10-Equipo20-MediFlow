import { createContext, useCallback, useContext, useEffect, useState } from "react";

import type { Rol } from "./roles";

/**
 * Vista de pared: la pantalla compartida de urgencias, leída a distancia. Barra lateral de iconos,
 * sin selector de rol ni firma a la vista, y cifras grandes. Por defecto para los roles de pantalla
 * compartida; la elección se recuerda por rol, así que apagarla en un rol no la apaga en otro.
 */
export interface EstadoPared {
  activo: boolean;
  alternar: () => void;
}

const Contexto = createContext<EstadoPared>({ activo: false, alternar: () => {} });
export const ProveedorPared = Contexto.Provider;

export function usePared(): EstadoPared {
  return useContext(Contexto);
}

function clave(rolId: string): string {
  return `mediflow.pared.${rolId}`;
}

function leer(rol: Rol): boolean {
  try {
    const v = localStorage.getItem(clave(rol.id));
    return v === null ? rol.pantallaCompartida : v === "si";
  } catch {
    return rol.pantallaCompartida;
  }
}

export function useEstadoPared(rol: Rol): EstadoPared {
  const [activo, setActivo] = useState(() => leer(rol));
  useEffect(() => { setActivo(leer(rol)); }, [rol]);
  const alternar = useCallback(() => {
    setActivo((actual) => {
      const nuevo = !actual;
      try { localStorage.setItem(clave(rol.id), nuevo ? "si" : "no"); } catch { /* vale para esta sesión */ }
      return nuevo;
    });
  }, [rol.id]);
  return { activo, alternar };
}
