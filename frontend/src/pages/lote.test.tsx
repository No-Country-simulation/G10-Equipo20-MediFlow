/** RN-P2: con el motor caído, la cola ofrece reintentar la lectura de todos los casos por fallo técnico de una vez. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";

const hace = (min: number) => new Date(Date.now() - min * 60000).toISOString();
const fallo = (id: string) => ({ documento_id: id, version: 1, nivel_prioridad: "Rutina", motivo_auditoria: "fallo_tecnico", campos_dudosos: [], tipo: "No Clasificable", creado_en: hace(20), plazo_minutos: 1440 });

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.spyOn(api, "colaRevision").mockResolvedValue([fallo("FT-1"), fallo("FT-2"), fallo("FT-3"), fallo("FT-4")] as never);
});
afterEach(() => vi.restoreAllMocks());

describe("reintento en lote desde la cola", () => {
  it("pide el reintento, informa cuántos se leyeron y recarga la cola", async () => {
    const reintentar = vi.spyOn(api, "reintentarFallos").mockResolvedValue({ candidatos: 4, leidos: ["FT-1", "FT-2", "FT-3", "FT-4"], fallidos: [], detenido: false, sin_intentar: 0 });
    render(<AppRouter rutaInicial="/revision" rolInicial="auditor_clinico" />);
    const banner = await screen.findByRole("button", { name: /reintentar la lectura de todos/i });
    const llamadasAntes = (api.colaRevision as unknown as { mock: { calls: unknown[] } }).mock.calls.length;  // la barra lateral también la pide
    (api.colaRevision as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue([]);
    await userEvent.click(banner);
    await waitFor(() => expect(reintentar).toHaveBeenCalled());
    expect(await screen.findByText(/4 de 4 casos leídos y enrutados/i)).toBeInTheDocument();
    await waitFor(() => expect((api.colaRevision as unknown as { mock: { calls: unknown[] } }).mock.calls.length).toBeGreaterThan(llamadasAntes));  // la cola se recarga
  });

  it("si el motor sigue caído lo dice y cuánto quedó sin intentar", async () => {
    vi.spyOn(api, "reintentarFallos").mockResolvedValue({ candidatos: 4, leidos: [], fallidos: ["FT-1", "FT-2", "FT-3"], detenido: true, sin_intentar: 1 });
    render(<AppRouter rutaInicial="/revision" rolInicial="auditor_clinico" />);
    await userEvent.click(await screen.findByRole("button", { name: /reintentar la lectura de todos/i }));
    const aviso = await screen.findByText(/el motor sigue caído/i);
    expect(aviso).toHaveTextContent("0 de 4");
    expect(aviso).toHaveTextContent("1 sin intentar");
    expect(within(screen.getByTestId("grupo-fallo-tecnico")).getAllByTestId("fila-cola")).toHaveLength(4);
  });
});
