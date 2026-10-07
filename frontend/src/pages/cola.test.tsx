/** Modo worker (RN-P2): la API acepta el documento con 202 y un worker aparte corre el triaje; la pantalla
 * muestra que está en cola, pregunta sola y, cuando hay resultado, lo enseña y recarga el historial. */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";
import { detalleCaso1 } from "../test/fixtures";
import type { TrabajoProcesamiento } from "../types";

vi.mock("../app/cola", async (original) => ({ ...(await original<typeof import("../app/cola")>()), INTERVALO_SONDEO_MS: 10 }));

const trabajo = (estado: TrabajoProcesamiento["estado"], intento = 0): TrabajoProcesamiento =>
  ({ id: 1, estado, intento, codigo_error: null, creado_en: null, actualizado_en: null, proximo_intento_en: null });
const recibido = () => detalleCaso1({ estado: "RECIBIDO", nivel_prioridad: null, resultado: null, alerta: null, trabajo: trabajo("EN_COLA") });
const enCurso = () => detalleCaso1({ estado: "VALIDADO", nivel_prioridad: null, resultado: null, alerta: null, trabajo: trabajo("EN_CURSO", 1) });
const terminado = () => detalleCaso1({ trabajo: trabajo("TERMINADO", 1) });

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
});
afterEach(() => vi.restoreAllMocks());

describe("cola persistente de procesamiento", () => {
  it("tras cargar, muestra que está en cola, pregunta sola y enseña el resultado cuando el worker termina", async () => {
    vi.spyOn(api, "enviarDocumento").mockResolvedValue(recibido());
    const consultar = vi.spyOn(api, "consultarDocumento").mockResolvedValueOnce(enCurso()).mockResolvedValue(terminado());
    render(<AppRouter rutaInicial="/documentos" rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /historial/i });
    await userEvent.click(screen.getByRole("button", { name: /pegar texto/i }));
    await userEvent.type(screen.getByLabelText(/texto clínico/i), "Paciente con disnea.");
    await userEvent.type(screen.getByLabelText(/id del documento/i), "DOC-CLIN-2026-8942");
    await userEvent.click(screen.getByRole("button", { name: /cargar documento/i }));
    expect(await screen.findByTestId("en-cola")).toHaveTextContent(/en cola/i);
    await waitFor(() => expect(consultar).toHaveBeenCalledTimes(2));
    const resultado = await screen.findByRole("status", { name: /resultado de la carga/i });
    await waitFor(() => expect(resultado).toHaveTextContent("Crítico"));
    expect(screen.queryByTestId("en-cola")).not.toBeInTheDocument();
    expect(api.listarDocumentos).toHaveBeenCalledTimes(3);  // al abrir, al cargar y al terminar el worker
  });

  it("el detalle avisa que todavía no hay resultado y se actualiza solo", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValueOnce(enCurso()).mockResolvedValue(terminado());
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="auditor_clinico" />);
    const aviso = await screen.findByTestId("en-cola");
    expect(aviso).toHaveTextContent(/procesando \(intento 1\)/i);
    await waitFor(() => expect(screen.queryByTestId("en-cola")).not.toBeInTheDocument());
    expect(await screen.findByRole("heading", { name: /^decisión/i })).toBeInTheDocument();
  });

  it("si el worker agotó los intentos, lo dice junto al resultado de la carga", async () => {
    vi.spyOn(api, "enviarDocumento").mockResolvedValue(detalleCaso1({ estado: "EN_REVISION_HUMANA", trabajo: trabajo("FALLIDO", 3) }));
    render(<AppRouter rutaInicial="/documentos" rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /historial/i });
    await userEvent.click(screen.getByRole("button", { name: /pegar texto/i }));
    await userEvent.type(screen.getByLabelText(/texto clínico/i), "x");
    await userEvent.type(screen.getByLabelText(/id del documento/i), "DOC-X");
    await userEvent.click(screen.getByRole("button", { name: /cargar documento/i }));
    expect(await screen.findByTestId("en-cola")).toHaveTextContent(/revisión humana por fallo técnico/i);
  });
});
