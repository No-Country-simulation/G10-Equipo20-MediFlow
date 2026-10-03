import { createContext, startTransition, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { cambiarMiClave, cerrarSesion, crearPrimerAdministrador, estadoSesion, EVENTO_SESION, iniciarSesion, listarRoles } from "../api";
import type { CuentaSesion } from "../types";
import { registrarRoles } from "./roles";

interface ContextoSesion {
  /** Cuenta que inició sesión; null cuando se trabaja sin sesión (modo demostración). */
  cuenta: CuentaSesion | null;
  /** La instalación no deja consultar ni firmar sin sesión (EXIGIR_SESION). */
  exigida: boolean;
  /** Cambia cuando llegan los roles del backend: quien derive algo de la lista de roles se vuelve a calcular. */
  versionRoles: number;
  /** La instalación no tiene ninguna cuenta: la pantalla de ingreso ofrece crear el primer administrador (RN-S3). */
  sinCuentas: boolean;
  nombreSede: string;
  crearPrimerAdministrador: (usuario: string, nombre: string, clave: string) => Promise<CuentaSesion>;
  cambiarClave: (claveActual: string, claveNueva: string) => Promise<CuentaSesion>;
  /** `alEntrar` corre con la cuenta ya validada y antes de que la interfaz cambie: es el momento de navegar. */
  ingresar: (usuario: string, clave: string, alEntrar?: (cuenta: CuentaSesion) => void) => Promise<CuentaSesion>;
  salir: () => Promise<void>;
}

const SIN_SESION: ContextoSesion = {
  cuenta: null,
  exigida: false,
  versionRoles: 0,
  sinCuentas: false,
  nombreSede: "",
  crearPrimerAdministrador: () => Promise.reject(new Error("sin proveedor de sesión")),
  cambiarClave: () => Promise.reject(new Error("sin proveedor de sesión")),
  ingresar: () => Promise.reject(new Error("sin proveedor de sesión")),
  salir: () => Promise.resolve(),
};

const Contexto = createContext<ContextoSesion>(SIN_SESION);

/**
 * Sesión del personal (RN-K5). Con sesión, el rol y la firma son los de la cuenta y no se eligen en pantalla.
 * Sin ella la aplicación sigue como en la demostración: el rol se elige y se firma con el nombre escrito.
 */
export function SesionProvider({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<{ cuenta: CuentaSesion | null; exigida: boolean; sinCuentas: boolean; nombreSede: string }>(
    { cuenta: null, exigida: false, sinCuentas: false, nombreSede: "" });
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
      .then((e) => setEstado((previo) => {
        const igual = previo.exigida === e.exigir_sesion && previo.cuenta?.usuario === e.sesion?.usuario && previo.cuenta?.rol === e.sesion?.rol
          && previo.cuenta?.debe_cambiar_clave === e.sesion?.debe_cambiar_clave && previo.sinCuentas === Boolean(e.sin_cuentas) && previo.nombreSede === (e.nombre_sede ?? "");
        return igual ? previo : { cuenta: e.sesion, exigida: e.exigir_sesion, sinCuentas: Boolean(e.sin_cuentas), nombreSede: e.nombre_sede ?? "" };
      }))
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
    crearPrimerAdministrador: async (usuario, nombre, clave) => {
      const cuenta = await crearPrimerAdministrador(usuario, nombre, clave);
      startTransition(() => setEstado((previo) => ({ ...previo, cuenta, sinCuentas: false })));
      return cuenta;
    },
    cambiarClave: async (claveActual, claveNueva) => {
      const cuenta = await cambiarMiClave(claveActual, claveNueva);
      startTransition(() => setEstado((previo) => ({ ...previo, cuenta })));
      return cuenta;
    },
  }), [estado, versionRoles]);

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSesion(): ContextoSesion {
  return useContext(Contexto);
}
