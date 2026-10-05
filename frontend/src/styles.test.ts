/**
 * Letra y foco con el estándar de salud elegido (NHS, WCAG 2.2): cuerpo de 16 px, ningún texto bajo 13 px
 * y un foco amarillo con anillo oscuro que se ve igual en los tres temas.
 */
import { describe, expect, it } from "vitest";

import css from "./styles.css?raw";

function enPixeles(valor: string): number | null {
  const rem = /^([\d.]+)rem$/.exec(valor);
  if (rem) return parseFloat(rem[1]) * 16;
  const px = /^([\d.]+)px$/.exec(valor);
  return px ? parseFloat(px[1]) : null;
}

const tamanos = [...css.matchAll(/font-size:\s*([^;}]+)/g)].map((m) => m[1].trim());

describe("tipografía (WCAG 1.4.4 y 1.4.12, NHS)", () => {
  it("lee la hoja de estilos", () => {
    expect(css.length).toBeGreaterThan(1000);
  });

  it("el cuerpo mide 16 px", () => {
    const body = /(?:^|\n)body\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";
    expect(body).toMatch(/font-size:\s*(1rem|16px)/);
  });

  it("ningún texto con tamaño fijo baja de 13 px", () => {
    expect(tamanos.filter((v) => (enPixeles(v) ?? 99) < 13)).toEqual([]);
  });

  it("los tamaños relativos más chicos que su contexto llevan un piso en rem", () => {
    expect(tamanos.filter((v) => /^[\d.]+em$/.test(v) && parseFloat(v) < 1)).toEqual([]);
  });
});

describe("foco visible (WCAG 2.4.7 y 2.4.11, NHS)", () => {
  it("es amarillo en los tres temas", () => {
    const focos = [...css.matchAll(/--foco:\s*([^;]+);/g)].map((m) => m[1].trim().toUpperCase());
    expect(focos.length).toBeGreaterThanOrEqual(3);
    expect(new Set(focos)).toEqual(new Set(["#FFD400"]));
  });

  it("lleva un anillo oscuro pegado al control para verse sobre fondos claros", () => {
    expect(css).toMatch(/--foco-anillo:\s*#/);
    expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:[^;]*var\(--foco\)[^}]*box-shadow:[^;]*var\(--foco-anillo\)/);
  });

  it("ninguna zona cambia el color del foco", () => {
    expect(css).not.toMatch(/:focus-visible\s*\{[^}]*outline-color/);
  });
});
