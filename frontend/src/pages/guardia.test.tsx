/** RN-L1: la cadena de guardia (RN-Q2) y el orden de canales (RN-P7) se configuran desde la pestaña Guardia y canales. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";

const CADENA = ["Jefe de Urgencias", "Coordinador Médico de Turno", "Dirección Médica"];
const CONFIGURACION = {
  vigente: { id: null, numero: 0, autor: "sistema", motivo: "valores iniciales", cambios: { umbrales: {}, ampliaciones: {} }, vigente_desde: null, estado: "vigente" },
  umbrales_base: {}, umbrales_efectivos: {}, rangos: {}, no_configurable: { news2: {} },
  listas: { alto_riesgo: { base: [], ampliadas: [] }, control_especial: { base: [], ampliadas: [] }, hallazgos_criticos: { base: [], ampliados: [] } },
  calidad: { limite_correccion_campo: 0.1, simulacion_ultimos: 50 },
  destinos: [],
  notificaciones: { cadena_guardia: CADENA, canales: ["Slack", "Correo"], base: { cadena_guardia: CADENA, canales: ["Slack", "Correo"] }, canales_conocidos: ["Slack", "Correo"], slack: {} },
  propuestas: [], historial: [],
};

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "obtenerConfiguracion").mockResolvedValue(CONFIGURACION as never);
});
afterEach(() => vi.restoreAllMocks());

async function abrirPestana() {
  render(<AppRouter rutaInicial="/configuracion" rolInicial="gestor" />);
  await userEvent.click(await screen.findByRole("tab", { name: /guardia y canales/i }));
  return screen.findByTestId("cadena-guardia");
}

describe("Guardia y canales (RN-L1)", () => {
  it("reordena, quita y agrega niveles de la cadena, y la propuesta lleva la cadena completa en orden", async () => {
    const proponer = vi.spyOn(api, "proponerConfiguracion").mockResolvedValue({ id: 3, numero: null, autor: "gestor.ana", motivo: "turnos", cambios: {}, toca_seguridad: true, aprobaciones: [], aprobaciones_requeridas: 2, estado: "propuesta" } as never);
    const panel = await abrirPestana();
    const niveles = within(panel).getByTestId("niveles");
    expect(niveles).toHaveTextContent("1. Jefe de Urgencias");
    expect(within(niveles).getByRole("button", { name: /subir jefe de urgencias/i })).toBeDisabled();
    expect(screen.getByTestId("barra-proponer")).toHaveTextContent(/sin cambios/i);

    await userEvent.click(within(niveles).getByRole("button", { name: /bajar jefe de urgencias/i }));
    expect(niveles).toHaveTextContent("1. Coordinador Médico de Turno");
    expect(screen.getByTestId("barra-proponer")).toHaveTextContent(/cadena de guardia: Coordinador Médico de Turno → Jefe de Urgencias → Dirección Médica/);
    await userEvent.click(within(niveles).getByRole("button", { name: /quitar dirección médica/i }));
    await userEvent.type(within(panel).getByLabelText(/nivel nuevo/i), "Médico de Turno");
    await userEvent.click(within(panel).getByRole("button", { name: /agregar al final/i }));
    expect(niveles).toHaveTextContent("3. Médico de Turno");

    await userEvent.type(screen.getByLabelText(/motivo de la versión/i), "turnos");
    await userEvent.click(screen.getByRole("button", { name: /proponer versión/i }));
    await waitFor(() => expect(proponer).toHaveBeenCalledWith({
      cambios: { umbrales: {}, ampliaciones: { alto_riesgo: [], control_especial: [], hallazgos_criticos: [] }, notificaciones: { cadena_guardia: ["Coordinador Médico de Turno", "Jefe de Urgencias", "Médico de Turno"] } },
      motivo: "turnos",
    }));
    expect(await screen.findByText(/toca seguridad: necesita dos aprobadores/i)).toBeInTheDocument();
  }, 15_000);

  it("quita y vuelve a agregar un canal, y sin canales no deja proponer", async () => {
    await abrirPestana();
    const canales = screen.getByTestId("canales");
    const orden = within(canales).getByTestId("orden-canales");
    expect(orden).toHaveTextContent("1. Slack");
    await userEvent.click(within(orden).getByRole("button", { name: /quitar slack/i }));
    expect(orden).toHaveTextContent("1. Correo");
    expect(screen.getByTestId("barra-proponer")).toHaveTextContent(/canales: Correo/);
    await userEvent.click(within(orden).getByRole("button", { name: /quitar correo/i }));
    expect(canales).toHaveTextContent(/hace falta al menos un canal/i);
    expect(screen.getByRole("button", { name: /simular/i })).toBeDisabled();
    await userEvent.click(within(canales).getByRole("button", { name: /agregar slack/i }));
    await userEvent.click(within(canales).getByRole("button", { name: /agregar correo/i }));
    expect(screen.getByTestId("barra-proponer")).toHaveTextContent(/sin cambios/i);  // el mismo orden de antes: nada que proponer
  });
});
