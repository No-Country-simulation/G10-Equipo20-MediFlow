/** RN-P2: cuando el motor no leyó el documento, la persona puede pedir que lo lea de nuevo en vez de transcribir a mano. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";
import { detalleCaso1, resultadoCaso1 } from "../test/fixtures";
import type { DocumentoDetalle } from "../types";

function enFalloTecnico(): DocumentoDetalle {
  const base = resultadoCaso1();
  const resultado = { ...base, estado: "EN_REVISION_HUMANA" as const,
    clasificacion: { ...base.clasificacion, tipo: "No Clasificable" as never },
    evaluacion: { requiere_auditoria_humana: true, motivo_auditoria: "fallo_tecnico", campos_dudosos: [] },
    enrutamiento: { ...base.enrutamiento, destino_principal: "Cola_Revision_Humana", destinos_secundarios: [], destinos_tras_revision: [] } };
  return detalleCaso1({ estado: "EN_REVISION_HUMANA", alerta: null, resultado: resultado as never, confianzas: {} });
}

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "consultarDocumento").mockResolvedValue(enFalloTecnico());
});
afterEach(() => vi.restoreAllMocks());

describe("reintentar la lectura tras un fallo técnico", () => {
  it("manda la acción reintentar y cierra el caso si el motor leyó bien", async () => {
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", resultado: resultadoCaso1() });
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /^decisión/i });
    const tarjeta = screen.getByTestId("reintento");
    await userEvent.click(within(tarjeta).getByRole("button", { name: /reintentar la lectura/i }));
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({ accion: "reintentar" })));
    expect(await screen.findByTestId("cierre-caso")).toHaveTextContent(/leído de nuevo y evaluado/i);
  });

  it("si el motor vuelve a fallar lo dice y el caso sigue en revisión", async () => {
    vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "EN_REVISION_HUMANA", resultado: enFalloTecnico().resultado! });
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /^decisión/i });
    await userEvent.click(within(screen.getByTestId("reintento")).getByRole("button", { name: /reintentar la lectura/i }));
    expect(await screen.findByText(/el motor volvió a fallar/i)).toBeInTheDocument();
    expect(screen.queryByTestId("cierre-caso")).not.toBeInTheDocument();
  });
});
