/**
 * PDF compuesto (RN-O4): el padre lista sus partes con su prioridad y estado, cada parte enlaza al padre,
 * y la carga deja declarar las páginas de cada documento.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";
import { detalleCaso1 } from "../test/fixtures";
import type { ItemListado } from "../types";

const AHORA = new Date().toISOString();
const PARTES: ItemListado[] = [
  { documento_id: "SOBRE-1", version: 1, estado: "ENRUTADO", nivel_prioridad: "Rutina", tipo_contenido: "pdf", formato: "pdf", nombre_archivo: "sobre_1.pdf", canal_origen: "Externo", creado_en: AHORA, tipo: "Receta Médica", motivo_auditoria: null, codigo_error: null, num_paginas: 1, documento_padre: "SOBRE" },
  { documento_id: "SOBRE-2", version: 1, estado: "ENRUTADO", nivel_prioridad: "Crítico", tipo_contenido: "pdf", formato: "pdf", nombre_archivo: "sobre_2.pdf", canal_origen: "Externo", creado_en: AHORA, tipo: "Epicrisis o Alta", motivo_auditoria: null, codigo_error: null, num_paginas: 2, documento_padre: "SOBRE" },
];

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: PARTES, total: 2, limit: 20, offset: 0 });
});
afterEach(() => vi.restoreAllMocks());

describe("PDF compuesto (RN-O4)", () => {
  it("el padre muestra sus partes con tipo, prioridad y estado, y enlaza a cada una", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(detalleCaso1({
      documento_id: "SOBRE", estado: "VALIDADO", nivel_prioridad: "Crítico", resultado: null, alerta: null, num_paginas: 3, nombre_archivo: "sobre.pdf", sub_documentos: PARTES,
    }));
    render(<AppRouter rutaInicial="/documentos/SOBRE" rolInicial="auditor_clinico" />);
    const seccion = await screen.findByTestId("sub-documentos");
    expect(seccion).toHaveTextContent("PDF compuesto: 2 sub-documentos");
    expect(seccion).toHaveTextContent(/la prioridad de este compuesto es la máxima de sus partes/i);
    const partes = within(seccion).getAllByTestId("sub-documento");
    expect(partes).toHaveLength(2);
    expect(partes[0]).toHaveTextContent("SOBRE-1");
    expect(partes[0]).toHaveTextContent("Receta médica");
    expect(partes[1]).toHaveTextContent("Crítico");
    expect(partes[1]).toHaveTextContent("2 pág");
    expect(within(partes[1]).getByRole("link", { name: /abrir/i })).toHaveAttribute("href", "/documentos/SOBRE-2");
  });

  it("una parte enlaza al PDF compuesto del que salió", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(detalleCaso1({ documento_id: "SOBRE-2", documento_padre: "SOBRE", alerta: null }));
    render(<AppRouter rutaInicial="/documentos/SOBRE-2" rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /^decisión/i });
    expect(screen.getByRole("link", { name: "SOBRE" })).toHaveAttribute("href", "/documentos/SOBRE");
    expect(screen.getByText(/parte del pdf compuesto/i)).toBeInTheDocument();
    expect(screen.queryByTestId("sub-documentos")).not.toBeInTheDocument();
  });

  it("el listado marca de qué compuesto salió cada parte", async () => {
    render(<AppRouter rutaInicial="/documentos" rolInicial="auditor_clinico" />);
    const filas = await screen.findAllByTestId("fila-documento");
    expect(filas[0]).toHaveTextContent("parte de SOBRE");
    expect(filas[1]).toHaveTextContent("parte de SOBRE");
  });

  it("al cargar un PDF se pueden declarar las páginas de cada documento y viajan con el archivo", async () => {
    const enviar = vi.spyOn(api, "enviarArchivo").mockResolvedValue(detalleCaso1({ documento_id: "SOBRE", estado: "VALIDADO", resultado: null, sub_documentos: PARTES }));
    render(<AppRouter rutaInicial="/documentos" rolInicial="auditor_clinico" />);
    await screen.findAllByTestId("fila-documento");
    const archivo = new File(["%PDF-1.4 sintetico"], "sobre.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByLabelText(/elegir archivo|archivo/i), archivo);
    const paginas = await screen.findByLabelText(/páginas por documento/i);
    await userEvent.type(paginas, "1-2,3");
    expect(screen.getByLabelText(/id del documento/i)).toHaveValue("SOBRE");  // el id sale del nombre del archivo
    await userEvent.click(screen.getByRole("button", { name: /cargar documento/i }));
    await waitFor(() => expect(enviar).toHaveBeenCalledWith(archivo, expect.objectContaining({ documento_id: "SOBRE", paginas_por_documento: "1-2,3" })));
  }, 15_000);
});
