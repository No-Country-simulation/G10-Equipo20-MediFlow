/**
 * Quinta crítica, vista de pared: la pantalla compartida de urgencias se lee a dos metros, dice si sus datos
 * están al día, nunca muestra calma sin datos y no expone el documento completo (RN-F1, RN-F2, RN-Q5, RN-K1).
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";
import css from "../styles.css?raw";
import { detalleCaso1 } from "../test/fixtures";

const hace = (min: number) => new Date(Date.now() - min * 60000).toISOString();

function alerta(id: string, concepto: string | null, minutos: number) {
  return { documento_id: id, version: 1, nivel: "Crítico", canal: "Slack", destinatario: "Jefe de Urgencias", mensaje: `Alerta Crítica. Doc: ${id}.`, concepto,
    emitida_en: hace(minutos), plazo_minutos: 15, estado_acuse: "pendiente", acusado_por: null, acusado_en: null, estado_documento: "EN_REVISION_HUMANA" };
}

const ESCALADAS = [alerta("DOC-A", "IAM_STEMI", 60), alerta("DOC-B", "TEP_AGUDO", 40)];

const RESUMEN = { total: 2, por_estado: { EN_REVISION_HUMANA: 2 }, por_prioridad: { "Crítico": 2 },
  en_revision: 2, alertas_sin_acuse: 2, recetas_por_verificar: 0, ordenes_por_autorizar: 0, enrutados: 0, entregados_hoy: 0 };

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.spyOn(api, "listarAlertas").mockResolvedValue(ESCALADAS as never);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "obtenerResumen").mockResolvedValue(RESUMEN as never);
});
afterEach(() => {
  vi.restoreAllMocks();
  document.documentElement.removeAttribute("data-contraste");
});

describe("la pared es la pantalla de alertas (RN-F1)", () => {
  it("en la pared, Inicio lleva directo a las alertas y sale del menú", async () => {
    render(<AppRouter rutaInicial="/inicio" rolInicial="jefe_urgencias" />);
    expect(await screen.findByRole("heading", { level: 1, name: /alertas críticas/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /hola/i })).toBeNull();
    const nav = screen.getByRole("navigation", { name: /principal/i });
    expect(within(nav).queryByRole("link", { name: /inicio/i })).toBeNull();
    expect(within(nav).getByRole("link", { name: /alertas críticas/i })).toBeInTheDocument();
  });

  it("fuera de la pared, el jefe de urgencias conserva su Inicio", async () => {
    try { localStorage.setItem("mediflow.pared.jefe_urgencias", "no"); } catch { /* sin storage */ }
    render(<AppRouter rutaInicial="/inicio" rolInicial="jefe_urgencias" />);
    expect(await screen.findByRole("heading", { name: /hola/i })).toBeInTheDocument();
  });

  it("la barra lateral de la pared muestra el nombre de cada destino y de cada control, no solo iconos", () => {
    // ninguna regla de la pared recorta el nombre de la navegación ni de los controles
    expect(css).not.toMatch(/\.pared \.lateral (\.texto-lateral|nav a \.etiqueta)[^{]*\{[^}]*clip/);
  });
});

describe("se lee a distancia y dice si está al día (RN-F2)", () => {
  it("el resumen dice que todas están escaladas y la nota no se repite aparte", async () => {
    render(<AppRouter rutaInicial="/alertas" rolInicial="jefe_urgencias" />);
    const resumen = await screen.findByTestId("resumen-pared");
    await waitFor(() => expect(resumen).toHaveTextContent(/2 sin acuse/));
    expect(resumen).toHaveTextContent(/todas escaladas al siguiente nivel de guardia/i);
    expect(screen.queryByTestId("nota-escalada")).toBeNull();
  });

  it("fuera de la pared, la nota de escaladas sigue en su lugar", async () => {
    render(<AppRouter rutaInicial="/alertas" rolInicial="auditor_clinico" />);
    expect(await screen.findByTestId("nota-escalada")).toHaveTextContent(/las 2 alertas pendientes están escaladas/i);
  });

  it("la línea de actualización dice que la pantalla está en vivo", async () => {
    render(<AppRouter rutaInicial="/alertas" rolInicial="jefe_urgencias" />);
    await waitFor(() => expect(screen.getByTestId("actualizado")).toHaveTextContent(/en vivo · actualizado a las/i));
  });

  it("si no puede actualizarse, una franja ancha lo dice antes del resumen, deja de decir en vivo y nunca muestra calma", async () => {
    vi.spyOn(api, "listarAlertas").mockRejectedValue(new Error("sin red"));
    render(<AppRouter rutaInicial="/alertas" rolInicial="jefe_urgencias" />);
    const franja = await screen.findByTestId("franja-desactualizada");
    expect(franja).toHaveTextContent(/datos desactualizados/i);
    expect(franja).toHaveAttribute("role", "alert");
    const resumen = screen.getByTestId("resumen-pared");
    expect(franja.compareDocumentPosition(resumen) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(resumen).not.toHaveTextContent(/ninguna alerta/i);
    expect(resumen).not.toHaveClass("en-calma");
    expect(screen.getByTestId("actualizado")).not.toHaveTextContent(/en vivo/i);
  });

  it("mientras carga por primera vez, el resumen tampoco muestra calma", async () => {
    vi.spyOn(api, "listarAlertas").mockReturnValue(new Promise(() => {}) as never);
    render(<AppRouter rutaInicial="/alertas" rolInicial="jefe_urgencias" />);
    const resumen = await screen.findByTestId("resumen-pared");
    expect(resumen).not.toHaveTextContent(/ninguna alerta/i);
    expect(resumen).not.toHaveClass("en-calma");
  });
});

describe("la columna Estado no queda vacía", () => {
  it("cuando todas las pendientes están escaladas, la columna desaparece y el estado sigue para el lector de pantalla", async () => {
    render(<AppRouter rutaInicial="/alertas" rolInicial="auditor_clinico" />);
    const filas = await screen.findAllByTestId("fila-alerta");
    expect(screen.queryByRole("columnheader", { name: /estado/i })).toBeNull();
    expect(filas[0]).toHaveTextContent(/estado: escalada/i);
  });

  it("con alertas todavía en plazo, la columna Estado vuelve", async () => {
    vi.spyOn(api, "listarAlertas").mockResolvedValue([alerta("DOC-A", "IAM_STEMI", 60), alerta("DOC-C", "TEP_AGUDO", 5)] as never);
    render(<AppRouter rutaInicial="/alertas" rolInicial="auditor_clinico" />);
    await screen.findAllByTestId("fila-alerta");
    expect(screen.getByRole("columnheader", { name: /estado/i })).toBeInTheDocument();
  });
});

describe("el detalle en la pared (RN-K1, RN-Q5)", () => {
  it("muestra la alerta con su acuse y deja el documento completo fuera de la pantalla compartida", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(detalleCaso1({ estado: "EN_REVISION_HUMANA" }));
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="jefe_urgencias" />);
    const alertaDoc = await screen.findByTestId("alerta-documento");
    expect(within(alertaDoc).getByRole("button", { name: /dar acuse/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /volver a alertas/i })).toHaveAttribute("href", "/alertas");
    expect(screen.getByTestId("documento-resguardado")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^original/i })).toBeNull();
    expect(screen.queryByRole("heading", { name: /^decisión/i })).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /salir de la vista de pared para revisarlo/i }));
    expect(await screen.findByRole("heading", { name: /^original/i })).toBeInTheDocument();
    expect(document.querySelector(".shell")).not.toHaveClass("pared");
  });

  it("en la pared, las teclas de decisión no actúan", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(detalleCaso1({ estado: "EN_REVISION_HUMANA" }));
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="jefe_urgencias" />);
    await screen.findByTestId("alerta-documento");
    await userEvent.keyboard("a");
    expect(screen.queryByText(/para decidir/i)).toBeNull();
    expect(screen.queryByTestId("confirmacion")).toBeNull();
  });
});
