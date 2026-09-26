import { useState } from "react";

const CLAVE = "mediflow.usuario";

/** Usuario que firma acciones (RN-G4, RN-Q5). Sin autenticación en el MVP: se escribe y se recuerda en este navegador. */
export function useUsuario(): [string, (u: string) => void] {
  const [usuario, setUsuarioEstado] = useState<string>(() => {
    try {
      return localStorage.getItem(CLAVE) ?? "";
    } catch {
      return "";
    }
  });
  const setUsuario = (u: string) => {
    setUsuarioEstado(u);
    try {
      localStorage.setItem(CLAVE, u);
    } catch {
      /* sin almacenamiento disponible */
    }
  };
  return [usuario, setUsuario];
}

export function enmascarar(valor: string | null | undefined): string {
  if (!valor) return "—";
  return valor
    .split(/\s+/)
    .map((p) => (p.length <= 1 ? p : p[0] + "▮".repeat(Math.min(6, p.length - 1))))
    .join(" ");
}
