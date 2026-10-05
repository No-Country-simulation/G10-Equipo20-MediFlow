/**
 * Acceso por rol: cada rol recibe la alarma de forma útil para su trabajo (RN-K1, RN-F1, RN-Q2)
 * y las bandejas de Farmacia y Autorizaciones dicen cuándo la caída del motor las deja incompletas (RN-P2).
 */
import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";

const hace = (min: number) => new Date(Date.now() - min * 60000).toISOString();

function alerta(id: string, minutos: number) {
  return { documento_id: id, version: 1, nivel: "Crítico", canal: "Slack", destinatario: "Jefe de Urgencias", mensaje: `Alerta Crítica. Doc: ${id}.`, concepto: "IAM_STEMI",
    emitida_en: hace(minutos), plazo_minutos: 15, estado_acuse: "pendiente", acusado_por: null, acusado_en: null, estado_documento: "EN_REVISION_HUMANA" };
}

function enFallo(id: string, minutos: number, nivel = "Rutina") {
  return { documento_id: id, version: 1, nivel_prioridad: nivel, motivo_auditoria: "fallo_tecnico", campos_dudosos: [], tipo: "No Clasificable",
    creado_en: hace(minutos), plazo_minutos: nivel === "Crítico" ? 15 : 1440, hallazgos: [] };
}

const CAIDA = [enFallo("DOC-1", 90), enFallo("DOC-2", 60), enFallo("DOC-3", 30, "Crítico")];

/** Deja terminar las cargas del shell (contadores y banner) antes de afirmar que algo no aparece. */
const esperarCargas = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.spyOn(api, "listarAlertas").mockResolvedValue([alerta("DOC-A", 40), alerta("DOC-B", 5)] as never);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "colaFarmacia").mockResolvedValue([]);
  vi.spyOn(api, "bandejaAutorizaciones").mockResolvedValue({ por_autorizar: [], avisos_urgencias: [] } as never);
});
afterEach(() => vi.restoreAllMocks());

describe("la alarma según quién puede atenderla (RN-K1, RN-F1, RN-Q2)", () => {
  it("el químico farmacéutico ve las alertas pendientes sin un enlace a una sección que no puede abrir, y sabe quién las atiende", async () => {
    render(<AppRouter rutaInicial="/farmacia" rolInicial="quimico_farmaceutico" />);
    const banner = await screen.findByRole("status", { name: /alertas críticas/i });
    expect(banner).toHaveTextContent(/2 alertas críticas sin acuse/i);
    expect(within(banner).queryByRole("link")).toBeNull();
    expect(banner).toHaveTextContent(/las atiende el auditor clínico o el jefe de urgencias/i);
  });

  it("el auditor de autorizaciones tampoco recibe un enlace a Alertas", async () => {
    render(<AppRouter rutaInicial="/autorizaciones" rolInicial="auditor_autorizaciones" />);
    const banner = await screen.findByRole("status", { name: /alertas críticas/i });
    expect(within(banner).queryByRole("link")).toBeNull();
    expect(banner).toHaveTextContent(/las atiende/i);
  });

  it("el auditor clínico, que sí puede dar acuse, conserva el enlace a Alertas", async () => {
    render(<AppRouter rutaInicial="/revision" rolInicial="auditor_clinico" />);
    const banner = await screen.findByRole("status", { name: /alertas críticas/i });
    expect(within(banner).getByRole("link", { name: /ver alertas/i })).toHaveAttribute("href", "/alertas");
    expect(banner).not.toHaveTextContent(/las atiende/i);
  });

  it("el botón del menú cuenta las alertas solo para quien puede atenderlas, y lo dice en su nombre", async () => {
    const { unmount } = render(<AppRouter rutaInicial="/revision" rolInicial="auditor_clinico" />);
    expect(await screen.findByRole("button", { name: /abrir menú.*2 alertas críticas sin acuse/i })).toBeInTheDocument();
    unmount();

    render(<AppRouter rutaInicial="/farmacia" rolInicial="quimico_farmaceutico" />);
    await screen.findByRole("status", { name: /alertas críticas/i });
    await esperarCargas();
    const menu = screen.getByRole("button", { name: /abrir menú/i });
    expect(menu).toHaveAccessibleName("Abrir menú");
    expect(within(menu).queryByText("2")).toBeNull();
  });
});

describe("Farmacia y Autorizaciones durante la caída del motor (RN-P2)", () => {
  it("Farmacia avisa que la caída retiene documentos y que su bandeja puede estar incompleta", async () => {
    vi.spyOn(api, "colaRevision").mockResolvedValue(CAIDA as never);
    render(<AppRouter rutaInicial="/farmacia" rolInicial="quimico_farmaceutico" />);
    const aviso = await screen.findByTestId("sistema-degradado");
    expect(aviso).toHaveTextContent(/no está respondiendo desde las \d/i);
    expect(aviso).toHaveTextContent(/3 documentos esperan transcripción/i);
    expect(aviso).toHaveTextContent(/recetas/i);
    expect(await screen.findByText(/ninguna receta lista para verificar/i)).toBeInTheDocument();
    expect(screen.queryByText(/no hay recetas por verificar/i)).toBeNull();
  });

  it("Autorizaciones avisa lo mismo con sus órdenes", async () => {
    vi.spyOn(api, "colaRevision").mockResolvedValue(CAIDA as never);
    render(<AppRouter rutaInicial="/autorizaciones" rolInicial="auditor_autorizaciones" />);
    const aviso = await screen.findByTestId("sistema-degradado");
    expect(aviso).toHaveTextContent(/3 documentos esperan transcripción/i);
    expect(aviso).toHaveTextContent(/órdenes/i);
    expect(await screen.findByText(/ninguna orden lista para autorizar/i)).toBeInTheDocument();
  });

  it("un fallo técnico suelto no es una caída: la bandeja no muestra el aviso", async () => {
    vi.spyOn(api, "colaRevision").mockResolvedValue([enFallo("DOC-1", 30)] as never);
    render(<AppRouter rutaInicial="/farmacia" rolInicial="quimico_farmaceutico" />);
    expect(await screen.findByText(/no hay recetas por verificar/i)).toBeInTheDocument();
    await esperarCargas();
    expect(screen.queryByTestId("sistema-degradado")).toBeNull();
  });
});
