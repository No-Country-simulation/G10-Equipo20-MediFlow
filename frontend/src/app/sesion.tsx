import { createContext, startTransition, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { cerrarSesion, estadoSesion, EVENTO_SESION, iniciarSesion, listarRoles } from "../api";
import type { CuentaSesion } from "../types";
import { registrarRoles } from "./roles";

interface ContextoSesion {
  /** Cuenta que inició sesión; null cuando se trabaja sin sesión (modo demostración). */
  cuenta: CuentaSesion | null;
  /** La instalación no deja consultar ni firmar sin sesión (EXIGIR_SESION). */
  exigida: boolean;
  /** Cambia cuando llegan los roles del backend: quien derive algo de la lista de roles se vuelve a calcular. */
  versionRoles: number;
  /** `alEntrar` corre con la cuenta ya validada y antes de que la interfaz cambie: es el momento de navegar. */
  ingresar: (usuario: string, clave: string, alEntrar?: (cuenta: CuentaSesion) => void) => Promise<CuentaSesion>;
  salir: () => Promise<void>;
}

const SIN_SESION: ContextoSesion = {
  cuenta: null,
  exigida: false,
  versionRoles: 0,
  ingresar: () => Promise.reject(new Error("sin proveedor de sesión")),
  salir: () => Promise.resolve(),
};

const Contexto = createContext<ContextoSesion>(SIN_SESION);

/**
 * Sesión del personal (RN-K5). Con sesión, el rol y la firma son los de la cuenta y no se eligen en pantalla.
 * Sin ella la aplicación sigue como en la demostración: el rol se elige y se firma con el nombre escrito.
 */
export function SesionProvider({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<{ cuenta: CuentaSesion | null; exigida: boolean }>({ cuenta: null, exigida: false });
  const [versionRoles, setVersionRoles] = useState(0);

  // Tabla K como datos (RN-K1): los roles vienen del backend; sin servidor queda el respaldo de la interfaz.
  useEffect(() => {
    let activo = true;
    listarRoles()
      .then((roles) => { if (activo && registrarRoles(roles) > 0) setVersionRoles((v) => v + 1); })
      .catch(() => { /* sin servidor: respaldo */ });
    return () => { activo = false; };
  }, []);

  const consultar = useCallback(() => {
    estadoSesion()
      .then((e) => setEstado((previo) => (previo.exigida === e.exigir_sesion && previo.cuenta?.usuario === e.sesion?.usuario && previo.cuenta?.rol === e.sesion?.rol
        ? previo
        : { cuenta: e.sesion, exigida: e.exigir_sesion })))
      .catch(() => { /* sin servidor: se sigue sin sesión y cada pantalla avisa por su cuenta */ });
  }, []);

  useEffect(() => {
    consultar();
    // La API avisa cuando una petición llega sin sesión válida (venció o la cerraron desde Administración).
    window.addEventListener(EVENTO_SESION, consultar);
    return () => window.removeEventListener(EVENTO_SESION, consultar);
  }, [consultar]);

  const valor = useMemo<ContextoSesion>(() => ({
    ...estado,
    versionRoles,
    ingresar: async (usuario, clave, alEntrar) => {
      const cuenta = await iniciarSesion(usuario, clave);
      alEntrar?.(cuenta);
      // El router cambia de ruta en una transición: la sesión entra en la misma, para que no se vea la pantalla anterior ya con sesión.
      startTransition(() => setEstado((previo) => ({ ...previo, cuenta })));
      return cuenta;
    },
    salir: async () => {
      await cerrarSesion().catch(() => undefined);
      setEstado((previo) => ({ ...previo, cuenta: null }));
    },
  }), [estado, versionRoles]);

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSesion(): ContextoSesion {
  return useContext(Contexto);
}
