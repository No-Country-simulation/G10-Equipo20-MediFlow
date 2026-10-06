/** Conjunto de referencia (RN-R2): el gestor ve cada corrección seudonimizada y puede descargar el conjunto. */
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";
import type { ConjuntoReferencia } from "../types";

const METRICAS = {
  periodo_dias: 30, calculado_en: new Date().toISOString(), documentos: 2, procesados: 2, por_estado: {}, por_prioridad: {}, tasa_automatizacion: 0.5,
  revision_por_motivo: {}, tiempo_por_etapa_s: {}, acuse_criticos: { emitidas: 0, acusadas: 0, pendientes: 0, minutos_promedio: null, dentro_de_plazo: 0, plazo_min: 15 },
  limite_correccion_campo: 0.1, correccion_por_campo: [], avisos: [], falsos_negativos_criticos: { n: 0, documentos: [], criticos_totales: 0, tasa: null }, versiones: {}, tokens: { entrada: 0, salida: 0 },
};
const REFERENCIA: ConjuntoReferencia = {
  resumen: { casos: 2, documentos: 2, por_campo: [{ campo: "extraccion.diagnosticos.*.cie10_sugerido", casos: 1 }, { campo: "nivel_prioridad", casos: 1 }], por_tipo: [], por_origen: { correccion: 2 }, subidos_a_critico: ["DOC-RUT-1"] },
  casos: [
    { id: 2, documento_id: "DOC-RUT-1", version: 1, origen: "correccion", campo: "nivel_prioridad", extraido: "Rutina", corregido: "Crítico", usuario: "aud.ana", tipo_documento: "Informe de Imágenes", canal_origen: "Externo", pais: "CO", nivel_propuesto: "Rutina", nivel_antes: "Rutina", nivel_resultante: "Crítico", hallazgos: [], modelo_llm: "gpt-4.1-mini", version_prompt: "triaje_v1", version_reglas: "8", version_pack: "8", creado_en: new Date().toISOString() },
    { id: 1, documento_id: "DOC-CRIT", version: 1, origen: "correccion", campo: "extraccion.diagnosticos[0].cie10_sugerido", extraido: "I26", corregido: "I26.0", usuario: "aud.ana", tipo_documento: "Informe de Imágenes", canal_origen: "Guardia_Emergencias", pais: "CO", nivel_propuesto: "Crítico", nivel_antes: "Crítico", nivel_resultante: "Crítico", hallazgos: ["TEP_AGUDO"], modelo_llm: "gpt-4.1-mini", version_prompt: "triaje_v1", version_reglas: "8", version_pack: "8", creado_en: new Date().toISOString() },
  ],
};

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "obtenerMetricas").mockResolvedValue(METRICAS as never);
  vi.spyOn(api, "obtenerReferencia").mockResolvedValue(REFERENCIA);
});
afterEach(() => vi.restoreAllMocks());

describe("Conjunto de referencia (RN-R2)", () => {
  it("lista cada corrección seudonimizada con la prioridad antes y después, y ofrece la descarga", async () => {
    render(<AppRouter rutaInicial="/metricas" rolInicial="gestor" />);
    const seccion = await screen.findByTestId("referencia");
    expect(seccion).toHaveTextContent("2 casos de 2 documentos");
    expect(seccion).toHaveTextContent("1 documento que una persona subió a Crítico");
    const filas = within(seccion).getAllByTestId("caso-referencia");
    expect(filas).toHaveLength(2);
    expect(filas[0]).toHaveTextContent("nivel_prioridad");
    expect(filas[0]).toHaveTextContent("Rutina → Crítico");
    expect(filas[1]).toHaveTextContent("I26 → I26.0");
    expect(within(seccion).getByRole("link", { name: /descargar el conjunto completo/i })).toHaveAttribute("href", "/api/metricas/referencia/exportar");
  });

  it("explica el conjunto vacío", async () => {
    vi.spyOn(api, "obtenerReferencia").mockResolvedValue({ resumen: { casos: 0, documentos: 0, por_campo: [], por_tipo: [], por_origen: {}, subidos_a_critico: [] }, casos: [] });
    render(<AppRouter rutaInicial="/metricas" rolInicial="gestor" />);
    const seccion = await screen.findByTestId("referencia");
    expect(seccion).toHaveTextContent(/todavía no hay correcciones humanas/i);
    expect(within(seccion).queryByRole("link", { name: /descargar/i })).not.toBeInTheDocument();
  });
});
