/**
 * Banco de trabajo: transcripción en fallo técnico, decisiones con confirmación,
 * atajos que se pueden apagar (WCAG 2.1.4), cierre de caso con "siguiente" y modo discreto que no filtra el diagnóstico.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";
import { detalleCaso1, resultadoCaso1 } from "../test/fixtures";
import type { DocumentoDetalle } from "../types";

const hace = (min: number) => new Date(Date.now() - min * 60000).toISOString();
const COLA = [
  { documento_id: "DOC-CLIN-2026-8942", version: 1, nivel_prioridad: "Crítico", motivo_auditoria: "critico_baja_confianza", campos_dudosos: [], tipo: "Informe de Imágenes", creado_en: hace(4), plazo_minutos: 15 },
  { documento_id: "DOC-DESPUES", version: 1, nivel_prioridad: "Rutina", motivo_auditoria: "campo_dudoso", campos_dudosos: [], tipo: "Receta Médica", creado_en: hace(2), plazo_minutos: 1440 },
];

function enRevision(cambios: Partial<DocumentoDetalle> = {}): DocumentoDetalle {
  const resultado = resultadoCaso1({
    estado: "EN_REVISION_HUMANA",
    evaluacion: { requiere_auditoria_humana: true, motivo_auditoria: "critico_baja_confianza", campos_dudosos: [] },
    enrutamiento: { ...resultadoCaso1().enrutamiento, destino_principal: "Cola_Revision_Humana", destinos_secundarios: [], destinos_tras_revision: ["Cola_Emergencia_Medica"] },
  });
  return detalleCaso1({ estado: "EN_REVISION_HUMANA", formato: "pdf", num_paginas: 1, nombre_archivo: "EPI-019_Hipoventilacion_obesidad.pdf", resultado, alerta: null, ...cambios });
}

function enFalloTecnico(): DocumentoDetalle {
  const base = enRevision();
  const resultado = { ...base.resultado!, evaluacion: { requiere_auditoria_humana: true, motivo_auditoria: "fallo_tecnico", campos_dudosos: [] },
    clasificacion: { ...base.resultado!.clasificacion, tipo: "No Clasificable" as never },
    enrutamiento: { ...base.resultado!.enrutamiento, destinos_tras_revision: [] } };
  return { ...base, resultado, confianzas: {} } as DocumentoDetalle;
}

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue(COLA as never);
  vi.spyOn(api, "consultarDocumento").mockResolvedValue(enRevision());
});
afterEach(() => vi.restoreAllMocks());

const RUTA = "/documentos/DOC-CLIN-2026-8942";

async function abrir(ruta = RUTA, firma = "ana") {
  render(<AppRouter rutaInicial={ruta} rolInicial="auditor_clinico" />);
  await screen.findByRole("heading", { name: /^decisión/i });
  if (firma) await userEvent.type(screen.getByLabelText(/firmo como/i), firma);
}

describe("decisiones con confirmación", () => {
  it("Aprobar pide confirmar, repite a dónde se enruta y se puede cancelar", async () => {
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", resultado: resultadoCaso1() });
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: /^aprobar/i }));
    const confirmar = screen.getByTestId("confirmacion");
    expect(confirmar).toHaveTextContent(/Cola_Emergencia_Medica|Emergencia/);
    expect(resolver).not.toHaveBeenCalled();
    await userEvent.click(within(confirmar).getByRole("button", { name: /cancelar/i }));
    expect(screen.queryByTestId("confirmacion")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^aprobar/i }));
    await userEvent.click(within(screen.getByTestId("confirmacion")).getByRole("button", { name: /confirmar aprobación/i }));
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({ accion: "aprobar", usuario: "ana" })));
  });

  it("la tecla A abre la confirmación, Enter confirma y Escape cancela", async () => {
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", resultado: resultadoCaso1() });
    await abrir();
    fireEvent.keyDown(document.body, { key: "a" });
    expect(screen.getByTestId("confirmacion")).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByTestId("confirmacion")).not.toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: "a" });
    expect(within(screen.getByTestId("confirmacion")).getByRole("button", { name: /confirmar aprobación/i })).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({ accion: "aprobar" })));
  });

  it("los atajos no se disparan con el foco en un botón y se pueden apagar (WCAG 2.1.4)", async () => {
    await abrir();
    const corregir = screen.getByRole("button", { name: /^corregir/i });
    corregir.focus();
    fireEvent.keyDown(corregir, { key: "a" });
    expect(screen.queryByTestId("confirmacion")).not.toBeInTheDocument();
    await userEvent.click(screen.getByText(/atajos de teclado/i));
    await userEvent.click(screen.getByLabelText(/usar atajos de una tecla/i));
    fireEvent.keyDown(document.body, { key: "a" });
    expect(screen.queryByTestId("confirmacion")).not.toBeInTheDocument();
  });

  it("al decidir, el caso se cierra con un resumen y el foco pasa a Siguiente caso", async () => {
    vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", resultado: resultadoCaso1() });
    const consultar = vi.spyOn(api, "consultarDocumento").mockResolvedValueOnce(enRevision()).mockResolvedValue(detalleCaso1({ estado: "ENRUTADO" }));
    await abrir(`${RUTA}?cola=1`);
    await userEvent.click(screen.getByRole("button", { name: /^aprobar/i }));
    await userEvent.click(screen.getByRole("button", { name: /confirmar aprobación/i }));
    const cierre = await screen.findByTestId("cierre-caso");
    expect(cierre).toHaveTextContent(/aprobado/i);
    const siguiente = within(cierre).getByRole("button", { name: /siguiente caso/i });
    await waitFor(() => expect(siguiente).toHaveFocus());
    await userEvent.click(siguiente);
    await waitFor(() => expect(consultar).toHaveBeenLastCalledWith("DOC-DESPUES"));
  });

  it("Rechazar explica por qué está deshabilitado", async () => {
    await abrir();
    const rechazar = screen.getByRole("button", { name: /^rechazar/i });
    expect(rechazar).toBeDisabled();
    expect(rechazar).toHaveAccessibleDescription(/motivo/i);
  });
});

describe("transcripción cuando el motor no leyó el documento", () => {
  it("muestra un formulario de transcripción en lugar de Aprobar y envía todo junto", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(enFalloTecnico());
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", resultado: resultadoCaso1() });
    await abrir();
    const panel = screen.getByTestId("transcripcion");
    expect(screen.queryByRole("button", { name: /^aprobar/i })).not.toBeInTheDocument();
    const guardar = within(panel).getByRole("button", { name: /guardar transcripción/i });
    expect(guardar).toBeDisabled();  // sin tipo de documento no se puede aplicar reglas
    await userEvent.selectOptions(within(panel).getByLabelText(/tipo de documento$/i), "Receta Médica");
    await userEvent.type(within(panel).getByLabelText(/fecha del documento/i), "03/04/2026");
    await userEvent.type(within(panel).getByLabelText(/número de documento/i), "41234567");
    await userEvent.type(within(panel).getByLabelText(/registro del profesional/i), "RM 78901");
    await userEvent.type(within(panel).getByLabelText(/^medicamento 1: dci/i), "losartan");
    await userEvent.type(within(panel).getByLabelText(/^medicamento 1: dosis/i), "50 mg");
    await userEvent.type(within(panel).getByLabelText(/^fc$/i), "72");
    await userEvent.click(guardar);
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({
      accion: "transcribir",
      transcripcion: expect.objectContaining({
        clasificacion: expect.objectContaining({ tipo: "Receta Médica", nivel_prioridad_propuesto: "Crítico" }),  // arranca en la prioridad actual
        extraccion: expect.objectContaining({
          fecha_documento: "03/04/2026",
          paciente: expect.objectContaining({ documento: expect.objectContaining({ valor: "41234567" }) }),
          profesional: expect.objectContaining({ registro_profesional: "RM 78901" }),
          medicamentos: [expect.objectContaining({ dci: "losartan", dosis: "50 mg" })],
          signos_vitales: expect.objectContaining({ FC: 72 }),
        }),
      }),
    })));
  });
});

describe("la transcripción nunca pasa de un paciente a otro", () => {
  it("J no cambia de documento con una transcripción sin guardar; al descartarla, el siguiente abre vacío", async () => {
    const siguiente = { ...enFalloTecnico(), documento_id: "DOC-DESPUES" } as DocumentoDetalle;
    const consultar = vi.spyOn(api, "consultarDocumento").mockImplementation(async (id: string) => (id === "DOC-DESPUES" ? siguiente : enFalloTecnico()));
    await abrir(`${RUTA}?cola=1`);
    const panel = screen.getByTestId("transcripcion");
    await userEvent.type(within(panel).getByLabelText(/nombre del paciente/i), "PACIENTE DEL DOCUMENTO A");
    (document.activeElement as HTMLElement).blur();
    fireEvent.keyDown(document.body, { key: "j" });
    expect(await screen.findByRole("alert")).toHaveTextContent(/transcripción sin guardar/i);
    expect(consultar).not.toHaveBeenCalledWith("DOC-DESPUES");
    await userEvent.click(within(panel).getByRole("button", { name: /descartar transcripción/i }));
    fireEvent.keyDown(document.body, { key: "j" });
    await waitFor(() => expect(consultar).toHaveBeenLastCalledWith("DOC-DESPUES"));
    await waitFor(() => expect(screen.getByText("DOC-DESPUES", { selector: ".id-doc code" })).toBeInTheDocument());
    expect(within(screen.getByTestId("transcripcion")).getByLabelText(/nombre del paciente/i)).toHaveValue("");
  });
});

describe("modo discreto", () => {
  it("oculta el nombre del archivo, que puede revelar el diagnóstico", async () => {
    render(<AppRouter rutaInicial={RUTA} rolInicial="jefe_urgencias" />);
    await screen.findByRole("heading", { name: /^decisión/i });
    expect(screen.queryByText(/Hipoventilacion/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/modo discreto/i));
    expect(screen.getByText(/Hipoventilacion/)).toBeInTheDocument();
  });
});
