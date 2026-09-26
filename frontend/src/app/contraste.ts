import { useEffect, useState } from "react";

const PREFIJO = "mediflow.contraste";

function leerPreferencia(clave: string): "alto" | "normal" | null {
  try {
    const v = localStorage.getItem(clave);
    return v === "alto" || v === "normal" ? v : null;
  } catch {
    return null;
  }
}

function sistemaPideContraste(): boolean {
  try {
    return typeof window.matchMedia === "function" && window.matchMedia("(prefers-contrast: more)").matches;
  } catch {
    return false;
  }
}

/**
 * Alto contraste para pantallas compartidas de urgencias. Orden de decisión: la elección manual
 * guardada en este navegador; si no hay, lo que pide el sistema operativo o el valor por defecto del rol.
 */
export function useAltoContraste(porDefectoDelRol: boolean, rolId = "general"): [boolean, () => void] {
  // Por rol: si alguien lo apaga en un rol, no queda apagado para la pantalla de urgencias.
  const clave = `${PREFIJO}.${rolId}`;
  const [preferencia, setPreferencia] = useState(() => leerPreferencia(clave));
  useEffect(() => { setPreferencia(leerPreferencia(clave)); }, [clave]);
  const activo = preferencia ? preferencia === "alto" : porDefectoDelRol || sistemaPideContraste();

  useEffect(() => {
    const raizDoc = document.documentElement;
    if (activo) raizDoc.setAttribute("data-contraste", "alto");
    else raizDoc.removeAttribute("data-contraste");
  }, [activo]);

  const alternar = () => {
    const nueva = activo ? "normal" : "alto";
    setPreferencia(nueva);
    try {
      localStorage.setItem(clave, nueva);
    } catch {
      /* sin almacenamiento: vale para esta sesión */
    }
  };
  return [activo, alternar];
}
