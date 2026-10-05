import type { KeyboardEvent } from "react";

/**
 * Patrón de pestañas de ARIA: las flechas recorren las pestañas y las activan; Inicio y Fin van a la primera
 * y a la última. Solo la pestaña activa está en el orden de tabulación, así Tab pasa directo al contenido.
 */
export function alTeclearPestanas(e: KeyboardEvent<HTMLElement>) {
  if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) return;
  const pestanas = [...e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')];
  const actual = pestanas.indexOf(document.activeElement as HTMLElement);
  if (actual < 0 || pestanas.length === 0) return;
  e.preventDefault();
  const destino = e.key === "Home" ? 0
    : e.key === "End" ? pestanas.length - 1
    : (actual + (e.key === "ArrowRight" ? 1 : -1) + pestanas.length) % pestanas.length;
  pestanas[destino].focus();
  pestanas[destino].click();
}
