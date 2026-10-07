/** El historial se acota por tipo documental, por rango de días y se ordena para revisión (lo más grave y más antiguo primero). */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
});
afterEach(() => vi.restoreAllMocks());

const ultimaLlamada = () => {
  const llamadas = (api.listarDocumentos as unknown as { mock: { calls: unknown[][] } }).mock.calls;
  return llamadas[llamadas.length - 1][0] as api.FiltrosListado;
};

describe("filtros del historial de documentos", () => {
  it("manda tipo, días y orden a la API y vuelve a la primera página", async () => {
    render(<AppRouter rutaInicial="/documentos" rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /historial/i });
    await waitFor(() => expect(api.listarDocumentos).toHaveBeenCalled());
    expect(ultimaLlamada().tipo).toBeUndefined();

    await userEvent.selectOptions(screen.getByLabelText(/^tipo$/i), "Receta Médica");
    await waitFor(() => expect(ultimaLlamada()).toMatchObject({ tipo: "Receta Médica", offset: 0 }));

    await userEvent.type(screen.getByLabelText(/^desde$/i), "2026-10-01");
    await userEvent.type(screen.getByLabelText(/^hasta$/i), "2026-10-07");
    await waitFor(() => expect(ultimaLlamada()).toMatchObject({ desde: "2026-10-01", hasta: "2026-10-07" }));

    await userEvent.selectOptions(screen.getByLabelText(/^orden$/i), "revision");
    await waitFor(() => expect(ultimaLlamada()).toMatchObject({ orden: "revision", tipo: "Receta Médica" }));
  });

  it("con el rango invertido avisa y no consulta", async () => {
    render(<AppRouter rutaInicial="/documentos" rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /historial/i });
    await waitFor(() => expect(api.listarDocumentos).toHaveBeenCalled());
    await userEvent.type(screen.getByLabelText(/^hasta$/i), "2026-10-01");
    await waitFor(() => expect(ultimaLlamada()).toMatchObject({ hasta: "2026-10-01" }));
    const antes = (api.listarDocumentos as unknown as { mock: { calls: unknown[] } }).mock.calls.length;
    await userEvent.type(screen.getByLabelText(/^desde$/i), "2026-10-07");
    expect(await screen.findByRole("alert")).toHaveTextContent(/no puede ser posterior/i);
    expect((api.listarDocumentos as unknown as { mock: { calls: unknown[] } }).mock.calls.length).toBe(antes);
  });
});
