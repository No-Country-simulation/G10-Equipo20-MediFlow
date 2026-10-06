/**
 * Reasignar y escalar desde la revisión (RN-J3) y el escalamiento por plazo vencido (RN-J2):
 * la cola dice quién tiene cada caso, y ninguna de las dos acciones cierra el caso.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";
import { detalleCaso1, resultadoCaso1 } from "../test/fixtures";
import type { DocumentoDetalle, ItemCola } from "../types";

const hace = (min: number) => new Date(Date.now() - min * 60000).toISOString();
const COLA: ItemCola[] = [
  { documento_id: "DOC-CLIN-2026-8942", version: 1, nivel_prioridad: "Crítico", motivo_auditoria: "critico_baja_confianza", campos_dudosos: [], tipo: "Informe de Imágenes", creado_en: hace(4), plazo_minutos: 15, asignado_a: "jefe.rojas", escalado_a_rol: null },
  { documento_id: "DOC-VENCIDO", version: 1, nivel_prioridad: "Rutina", motivo_auditoria: "campo_dudoso", campos_dudosos: [], tipo: "Receta Médica", creado_en: hace(30 * 60), plazo_minutos: 1440, asignado_a: null, escalado_a_rol: "jefe_urgencias" },
  { documento_id: "DOC-LIBRE", version: 1, nivel_prioridad: "Rutina", motivo_auditoria: "campo_dudoso", campos_dudosos: [], tipo: "Receta Médica", creado_en: hace(2), plazo_minutos: 1440, asignado_a: null, escalado_a_rol: null },
];
const REVISORES = [
  { usuario: "aud.ana", nombre: "Ana Auditora", rol: "auditor_clinico" },
  { usuario: "jefe.rojas", nombre: "Jefe Rojas", rol: "jefe_urgencias" },
];

function enRevision(cambios: Partial<DocumentoDetalle> = {}): DocumentoDetalle {
  const resultado = resultadoCaso1({
    estado: "EN_REVISION_HUMANA",
    evaluacion: { requiere_auditoria_humana: true, motivo_auditoria: "critico_baja_confianza", campos_dudosos: [] },
    enrutamiento: { ...resultadoCaso1().enrutamiento, destino_principal: "Cola_Revision_Humana", destinos_secundarios: [], destinos_tras_revision: ["Cola_Emergencia_Medica"] },
  });
  return detalleCaso1({ estado: "EN_REVISION_HUMANA", formato: "pdf", num_paginas: 1, nombre_archivo: "informe.pdf", resultado, alerta: null, ...cambios });
}

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue(COLA);
  vi.spyOn(api, "listarRevisores").mockResolvedValue(REVISORES);
  vi.spyOn(api, "consultarDocumento").mockResolvedValue(enRevision());
});
afterEach(() => vi.restoreAllMocks());

const RUTA = "/documentos/DOC-CLIN-2026-8942";

async function abrir(rol: "auditor_clinico" | "jefe_urgencias" = "auditor_clinico") {
  render(<AppRouter rutaInicial={RUTA} rolInicial={rol} />);
  await screen.findByRole("heading", { name: /^decisión/i });
}

describe("la cola dice quién tiene cada caso", () => {
  it("muestra el revisor asignado y el rol al que escaló; un caso libre no lleva etiqueta (RN-J3, RN-J2)", async () => {
    render(<AppRouter rutaInicial="/revision" rolInicial="auditor_clinico" />);
    const filas = await screen.findAllByTestId("fila-cola");
    expect(filas[0]).toHaveTextContent("Asignado a jefe.rojas");
    expect(filas[1]).toHaveTextContent("Escalado a Jefe de urgencias");
    expect(filas[2]).not.toHaveTextContent(/asignado|escalado/i);
  });
});

describe("reasignar", () => {
  it("elige un revisor de la lista, manda asignar_a y el caso sigue abierto", async () => {
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "EN_REVISION_HUMANA", resultado: resultadoCaso1() });
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: /^reasignar/i }));
    const tarjeta = await screen.findByTestId("reasignacion");
    const selector = within(tarjeta).getByLabelText(/reasignar a/i);
    await waitFor(() => expect(within(selector).getByRole("option", { name: /jefe rojas · jefe de urgencias/i })).toBeInTheDocument());
    expect(within(selector).getByRole("option", { name: /ana auditora .*\(yo\)/i })).toBeInTheDocument();
    const confirmar = within(tarjeta).getByRole("button", { name: /confirmar reasignación/i });
    expect(confirmar).toBeDisabled();
    await userEvent.selectOptions(selector, "jefe.rojas");
    await userEvent.click(confirmar);
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({ accion: "reasignar", asignar_a: "jefe.rojas" })));
    expect(await screen.findByText(/reasignado a jefe\.rojas\. sigue en revisión/i)).toBeInTheDocument();
    expect(screen.queryByTestId("cierre-caso")).not.toBeInTheDocument();
    await waitFor(() => expect(api.consultarDocumento).toHaveBeenCalledTimes(2));
  });

  it("se puede cancelar sin enviar nada", async () => {
    const resolver = vi.spyOn(api, "resolverRevision");
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: /^reasignar/i }));
    await userEvent.click(within(screen.getByTestId("reasignacion")).getByRole("button", { name: /cancelar/i }));
    expect(screen.queryByTestId("reasignacion")).not.toBeInTheDocument();
    expect(resolver).not.toHaveBeenCalled();
  });
});

describe("escalar", () => {
  it("exige motivo, pide confirmación con el rol de destino y no cierra el caso (RN-J3)", async () => {
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "EN_REVISION_HUMANA", resultado: resultadoCaso1() });
    await abrir();
    const escalar = screen.getByRole("button", { name: /^escalar/i });
    expect(escalar).toBeDisabled();
    expect(escalar).toHaveAccessibleDescription(/motivo/i);
    await userEvent.type(screen.getByLabelText(/^motivo/i), "hallazgo fuera de mi criterio");
    await userEvent.click(escalar);
    const confirmacion = screen.getByTestId("confirmacion");
    expect(confirmacion).toHaveTextContent(/escalar DOC-CLIN-2026-8942 a Jefe de urgencias/i);
    expect(confirmacion).toHaveTextContent("«hallazgo fuera de mi criterio»");
    await userEvent.click(within(confirmacion).getByRole("button", { name: /confirmar escalamiento/i }));
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({ accion: "escalar", motivo: "hallazgo fuera de mi criterio" })));
    expect(await screen.findByText(/escalado a jefe de urgencias\. sigue en revisión/i)).toBeInTheDocument();
    expect(screen.queryByTestId("cierre-caso")).not.toBeInTheDocument();
  });

  it("un caso ya escalado muestra a qué rol y no se vuelve a escalar; el jefe tampoco tiene a quién escalar", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(enRevision({ escalado_a_rol: "jefe_urgencias" }));
    await abrir();
    expect(screen.getByTestId("asignacion")).toHaveTextContent("Escalado a Jefe de urgencias");
    expect(screen.queryByRole("button", { name: /^escalar/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reasignar/i })).toBeEnabled();  // el jefe lo devuelve a un auditor
  });

  it("el jefe de urgencias no ve Escalar: por encima no hay otro rol (RN-J2)", async () => {
    try { localStorage.setItem("mediflow.pared.jefe_urgencias", "no"); } catch { /* sin storage */ }  // fuera de la vista de pared
    await abrir("jefe_urgencias");
    expect(screen.queryByRole("button", { name: /^escalar/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reasignar/i })).toBeInTheDocument();
  });
});
