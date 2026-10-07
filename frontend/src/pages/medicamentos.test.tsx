/**
 * Corrección de medicamentos desde el banco de trabajo (RN-J4, RN-J8, RN-CO8): cada campo cambiado viaja como su
 * propia corrección; agregar o quitar un medicamento reemplaza la lista completa.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";
import { detalleCaso1, resultadoCaso1 } from "../test/fixtures";
import type { DocumentoDetalle, Medicamento } from "../types";

const ACETAMINOFEN: Medicamento = { dci: "acetaminofen", dosis: "500 mg", dosis_valor: "500", via: "VO", frecuencia: "Cada 8 horas", duracion: "5 días si dolor", unidades_por_toma: null, alto_riesgo: false, control_especial: false };
const NAPROXENO: Medicamento = { dci: "naproxeno", dosis: "250 mg", dosis_valor: "250", via: "VO", frecuencia: "Cada 12 h", unidades_por_toma: null, alto_riesgo: false, control_especial: false };

function recetaEnRevision(): DocumentoDetalle {
  const base = resultadoCaso1();
  const resultado = {
    ...base, estado: "EN_REVISION_HUMANA" as const,
    clasificacion: { ...base.clasificacion, tipo: "Epicrisis o Alta" as never, nivel_prioridad: "Rutina" as const },
    extraccion: { ...base.extraccion, medicamentos: [ACETAMINOFEN, NAPROXENO], hallazgos_criticos_detectados: [] },
    evaluacion: { requiere_auditoria_humana: true, motivo_auditoria: "campo_dudoso", campos_dudosos: ["medicamento_dosis"] },
    enrutamiento: { ...base.enrutamiento, destino_principal: "Cola_Revision_Humana", destinos_secundarios: [], destinos_tras_revision: ["Historia_Clinica_Electronica"] },
  };
  return detalleCaso1({ estado: "EN_REVISION_HUMANA", nivel_prioridad: "Rutina", alerta: null, resultado: resultado as never,
    confianzas: { identidad_paciente: 0.95, medicamento_dosis: 0.9, diagnostico_codigo: 0.9, profesional: 0.95 },
    umbrales: { clasificacion: 0.85, identidad_paciente: 0.95, medicamento_dosis: 0.95, diagnostico_codigo: 0.9, profesional: 0.85, resto: 0.8 } });
}

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "consultarDocumento").mockResolvedValue(recetaEnRevision());
});
afterEach(() => vi.restoreAllMocks());

async function abrirEditor() {
  render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="auditor_clinico" />);
  await screen.findByRole("heading", { name: /^decisión/i });
  const bloque = screen.getByTestId("campo-medicamento_dosis");
  expect(bloque).toHaveTextContent("acetaminofen · 500 mg · VO · Cada 8 horas · 5 días si dolor");
  await userEvent.click(within(bloque).getByRole("button", { name: /corregir/i }));
  return screen.findByTestId("editor-medicamentos");
}

describe("corrección de medicamentos", () => {
  it("corrige las unidades por toma del medicamento elegido y manda solo ese campo", async () => {
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", resultado: resultadoCaso1() });
    const editor = await abrirEditor();
    const aplicar = within(editor).getByRole("button", { name: /aplicar corrección/i });
    expect(aplicar).toBeDisabled();
    expect(within(editor).getByLabelText(/medicamento a corregir/i)).toHaveValue("0");
    await userEvent.type(within(editor).getByLabelText(/unidades por toma/i), "2 tabletas");
    expect(editor).toHaveTextContent("1 campo corregido");
    await userEvent.click(aplicar);
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({
      accion: "corregir", correcciones: { "extraccion.medicamentos[0].unidades_por_toma": "2 tabletas" },
    })));
  }, 15_000);

  it("corregir el segundo medicamento muestra el valor leído y usa su índice", async () => {
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", resultado: resultadoCaso1() });
    const editor = await abrirEditor();
    await userEvent.selectOptions(within(editor).getByLabelText(/medicamento a corregir/i), "1");
    const frecuencia = within(editor).getByLabelText(/frecuencia/i);
    expect(frecuencia).toHaveValue("Cada 12 h");
    await userEvent.clear(frecuencia);
    await userEvent.type(frecuencia, "Cada 12 h con alimentos");
    expect(editor).toHaveTextContent("leído: Cada 12 h");
    await userEvent.click(within(editor).getByRole("button", { name: /aplicar corrección/i }));
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({
      correcciones: { "extraccion.medicamentos[1].frecuencia": "Cada 12 h con alimentos" },
    })));
  }, 15_000);

  it("agregar o quitar un medicamento reemplaza la lista completa, y sin DCI no deja aplicar", async () => {
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", resultado: resultadoCaso1() });
    const editor = await abrirEditor();
    await userEvent.click(within(editor).getByRole("button", { name: /agregar medicamento/i }));
    const aplicar = within(editor).getByRole("button", { name: /aplicar corrección/i });
    expect(aplicar).toBeDisabled();
    expect(editor).toHaveTextContent(/cada medicamento necesita su dci/i);
    await userEvent.type(within(editor).getByLabelText(/medicamento \(dci\)/i), "omeprazol");
    await userEvent.type(within(editor).getByLabelText(/concentración o dosis/i), "20 mg");
    expect(editor).toHaveTextContent(/se reemplaza la lista completa/i);
    await userEvent.selectOptions(within(editor).getByLabelText(/medicamento a corregir/i), "1");
    await userEvent.click(within(editor).getByRole("button", { name: /quitar este medicamento/i }));
    expect(editor).toHaveTextContent(/se quitará de la lectura/i);
    await userEvent.click(aplicar);
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({
      correcciones: { "extraccion.medicamentos": [
        expect.objectContaining({ dci: "acetaminofen", dosis: "500 mg", unidades_por_toma: null }),
        expect.objectContaining({ dci: "omeprazol", dosis: "20 mg", via: null }),
      ] },
    })));
  }, 15_000);
});
