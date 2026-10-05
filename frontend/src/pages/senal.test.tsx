/**
 * Señal clínica: la señal clínica primero, una transcripción que no induce a error
 * y acciones repetidas que no pierden el contexto ni el foco.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";
import { detalleCaso1, resultadoCaso1 } from "../test/fixtures";
import type { DocumentoDetalle } from "../types";

const hace = (min: number) => new Date(Date.now() - min * 60000).toISOString();

function alerta(id: string, concepto: string | null, minutos: number) {
  return { documento_id: id, version: 1, nivel: "Crítico", canal: "Slack", destinatario: "Jefe de Urgencias", mensaje: `Alerta Crítica. Doc: ${id}.`, concepto,
    emitida_en: hace(minutos), plazo_minutos: 15, estado_acuse: "pendiente", acusado_por: null, acusado_en: null, estado_documento: "EN_REVISION_HUMANA" };
}

function enFalloTecnico(cambios: Partial<DocumentoDetalle> = {}): DocumentoDetalle {
  const base = resultadoCaso1();
  const resultado = { ...base, estado: "EN_REVISION_HUMANA" as never, evaluacion: { requiere_auditoria_humana: true, motivo_auditoria: "fallo_tecnico", campos_dudosos: [] },
    clasificacion: { ...base.clasificacion, tipo: "No Clasificable" as never }, enrutamiento: { ...base.enrutamiento, destinos_tras_revision: [] } };
  return detalleCaso1({ estado: "EN_REVISION_HUMANA", formato: "pdf", num_paginas: 1, resultado: resultado as never, confianzas: {}, alerta: null, ...cambios });
}

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
});
afterEach(() => vi.restoreAllMocks());

describe("la señal clínica primero", () => {
  it("la cola muestra el hallazgo como texto principal y el ID como dato secundario", async () => {
    vi.spyOn(api, "colaRevision").mockResolvedValue([
      { documento_id: "DOC-TEP", version: 1, nivel_prioridad: "Crítico", motivo_auditoria: "critico_baja_confianza", campos_dudosos: [], tipo: "Informe de Imágenes", creado_en: hace(3), plazo_minutos: 15, hallazgos: ["TEP_AGUDO"] },
      { documento_id: "DOC-SIN", version: 1, nivel_prioridad: "Rutina", motivo_auditoria: "campo_dudoso", campos_dudosos: [], tipo: "No Clasificable", creado_en: hace(3), plazo_minutos: 1440, hallazgos: [] },
    ] as never);
    render(<AppRouter rutaInicial="/revision" rolInicial="auditor_clinico" />);
    const [tep, sin] = await screen.findAllByTestId("fila-cola");
    expect(within(tep).getByText("Tromboembolismo pulmonar agudo")).toHaveClass("principal");
    expect(within(tep).getByRole("link", { name: /revisar/i })).toHaveTextContent("DOC-TEP");
    expect(within(sin).getByText("No clasificable")).toHaveClass("principal");  // mayúscula a la española
  });

  it("el título del detalle es el hallazgo y el ID queda como dato", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(detalleCaso1());
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="auditor_clinico" />);
    expect(await screen.findByRole("heading", { level: 1, name: /tromboembolismo pulmonar agudo/i })).toBeInTheDocument();
    expect(screen.getByText("DOC-CLIN-2026-8942", { selector: ".id-doc code" })).toBeInTheDocument();
  });

  it("cuando todas las pendientes están escaladas se dice una vez y un concepto vacío se nombra", async () => {
    vi.spyOn(api, "listarAlertas").mockResolvedValue([alerta("DOC-A", "IAM_STEMI", 60), alerta("DOC-B", null, 90)] as never);
    render(<AppRouter rutaInicial="/alertas" rolInicial="auditor_clinico" />);
    const filas = await screen.findAllByTestId("fila-alerta");
    expect(screen.getByText(/las 2 alertas pendientes están escaladas/i)).toBeInTheDocument();
    expect(within(filas[0]).queryByText(/^escalada$/i)).not.toBeInTheDocument();
    expect(within(filas[0]).getByText(/hallazgo sin identificar/i)).toBeInTheDocument();
  });

  it("la vista de pared no esconde alertas en silencio: avisa cuántas más hay", async () => {
    vi.spyOn(api, "listarAlertas").mockResolvedValue(Array.from({ length: 10 }, (_, i) => alerta(`DOC-${i}`, "TEP_AGUDO", 20 + i)) as never);
    render(<AppRouter rutaInicial="/alertas" rolInicial="jefe_urgencias" />);
    await waitFor(() => expect(screen.getAllByTestId("fila-alerta")).toHaveLength(8));
    await userEvent.click(screen.getByRole("button", { name: /mostrar las 2 alertas más/i }));
    expect(screen.getAllByTestId("fila-alerta")).toHaveLength(10);
  });
});

describe("transcripción que no induce a error", () => {
  it("la prioridad arranca en la actual, los ejemplos van fuera de los campos y hay cabeceras de medicamentos", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(enFalloTecnico());
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="auditor_clinico" />);
    const panel = await screen.findByTestId("transcripcion");
    expect(within(panel).getByLabelText(/prioridad que indica el documento/i)).toHaveValue("Crítico");
    const cie = within(panel).getByLabelText(/código cie-10/i);
    expect(cie).not.toHaveAttribute("placeholder");
    expect(cie).toHaveAccessibleDescription(/ej\.: i10/i);
    await userEvent.selectOptions(within(panel).getByLabelText(/tipo de documento$/i), "Receta Médica");
    expect(within(panel).getByTestId("cabecera-medicamentos")).toHaveTextContent(/dosis/i);
    expect(within(panel).getByLabelText(/^medicamento 1: dosis/i)).not.toHaveAttribute("placeholder");
  });

  it("al guardar, el cierre dice la prioridad resultante y si hay alerta", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(enFalloTecnico());
    vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", resultado: resultadoCaso1() });
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="auditor_clinico" />);
    await userEvent.type(await screen.findByLabelText(/firmo como/i), "ana");
    const panel = screen.getByTestId("transcripcion");
    await userEvent.selectOptions(within(panel).getByLabelText(/tipo de documento$/i), "Informe de Imágenes");
    await userEvent.click(within(panel).getByRole("button", { name: /guardar transcripción/i }));
    const cierre = await screen.findByTestId("cierre-caso");
    expect(cierre).toHaveTextContent(/prioridad resultante: crítico/i);
    expect(cierre).toHaveTextContent(/alerta/i);
  });

  it("en modo discreto lo que se escribe del paciente queda enmascarado", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(enFalloTecnico());
    try { localStorage.setItem("mediflow.pared.jefe_urgencias", "no"); } catch { /* sin storage */ }
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="jefe_urgencias" />);
    const panel = await screen.findByTestId("transcripcion");
    expect(within(panel).getByLabelText(/nombre del paciente/i)).toHaveClass("enmascarado");
    expect(within(panel).getByLabelText(/número de documento del paciente/i)).toHaveClass("enmascarado");
  });
});

describe("acciones repetidas con contexto y foco", () => {
  it("Dar acuse nombra el hallazgo y el documento, y tras el acuse el foco va al resultado", async () => {
    vi.spyOn(api, "listarAlertas").mockResolvedValue([alerta("DOC-A", "IAM_STEMI", 5)] as never);
    vi.spyOn(api, "acusarAlerta").mockResolvedValue({ estado_acuse: "acusado", acusado_por: "ana", estado: "EN_REVISION_HUMANA" });
    render(<AppRouter rutaInicial="/alertas" rolInicial="auditor_clinico" />);
    await userEvent.click(await screen.findByRole("button", { name: /dar acuse: infarto con elevación del st, DOC-A/i }));
    await userEvent.type(screen.getByLabelText(/quién da el acuse/i), "ana");
    await userEvent.click(screen.getByRole("button", { name: /confirmar acuse/i }));
    await waitFor(() => expect(screen.getByText(/circuito cerrado/i)).toHaveFocus());
  });

  it("sin firma, A avisa en vez de no hacer nada, y un enlace lleva directo a Firmo como", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(detalleCaso1({ estado: "EN_REVISION_HUMANA", resultado: resultadoCaso1({ estado: "EN_REVISION_HUMANA",
      evaluacion: { requiere_auditoria_humana: true, motivo_auditoria: "campo_dudoso", campos_dudosos: [] },
      enrutamiento: { ...resultadoCaso1().enrutamiento, destinos_tras_revision: ["Cola_Emergencia_Medica"] } }), alerta: null }));
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /^decisión/i });
    fireEvent.keyDown(document.body, { key: "a" });
    expect(await screen.findByRole("alert")).toHaveTextContent(/firmo como/i);
    await userEvent.click(screen.getByRole("button", { name: /escribir mi usuario/i }));
    expect(screen.getByLabelText(/firmo como/i)).toHaveFocus();
  });
});
