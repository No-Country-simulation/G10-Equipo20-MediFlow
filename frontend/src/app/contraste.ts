import { useEffect, useState } from "react";

const CLAVE = "mediflow.contraste";

function leerPreferencia(): "alto" | "normal" | null {
  try {
    const v = localStorage.getItem(CLAVE);
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
export function useAltoContraste(porDefectoDelRol: boolean): [boolean, () => void] {
  const [preferencia, setPreferencia] = useState(leerPreferencia);
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
      localStorage.setItem(CLAVE, nueva);
    } catch {
      /* sin almacenamiento: vale para esta sesión */
    }
  };
  return [activo, alternar];
}
