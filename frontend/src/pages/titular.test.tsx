/**
 * Solicitudes del titular (RN-M6): se registran en la ficha del paciente, se responden con firma dentro del plazo,
 * se ven pendientes en el directorio y avisan al revisor al abrir el documento.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";
import { detalleCaso1 } from "../test/fixtures";
import type { SolicitudTitular } from "../types";

const AHORA = new Date().toISOString();
const EN_DIEZ_DIAS = new Date(Date.now() + 10 * 86400000).toISOString();
const AYER = new Date(Date.now() - 86400000).toISOString();
const ANA = { id: 4, pais: "CO", tipo_documento: "CC", numero_documento: "41234567", nombre: "Ana María Pérez", edad: 58, sexo: "F", documentos: 2, creado_en: AHORA, actualizado_en: AHORA };
const PENDIENTE: SolicitudTitular = {
  id: 7, paciente_id: 4, paciente_nombre: "Ana María Pérez", documento_id: "REC-2", version: 1, presentada_por: "representante", canal: "escrito",
  motivo: "no está de acuerdo con la prioridad", registrada_por: "aud.ana", registrada_en: AHORA, vence_en: EN_DIEZ_DIAS,
  estado: "pendiente", resultado: null, respuesta: null, respondida_por: null, respondida_en: null,
};
const FICHA = {
  ...ANA,
  historial: [],
  solicitudes: [] as SolicitudTitular[],
  documentos_listado: [
    { documento_id: "REC-2", version: 1, estado: "ENRUTADO", nivel_prioridad: "Rutina", tipo: "Receta Médica", fecha_documento: "03/04/2026", creado_en: AHORA },
    { documento_id: "EPI-1", version: 2, estado: "ENTREGADO", nivel_prioridad: "Crítico", tipo: "Epicrisis o Alta", fecha_documento: null, creado_en: AHORA },
  ],
};

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.spyOn(api, "listarPacientes").mockResolvedValue({ items: [ANA], total: 1, limit: 20, offset: 0 } as never);
  vi.spyOn(api, "obtenerPaciente").mockResolvedValue(FICHA as never);
  vi.spyOn(api, "listarSolicitudesTitular").mockResolvedValue([]);
});
afterEach(() => vi.restoreAllMocks());

describe("registrar la solicitud en la ficha", () => {
  it("elige el documento, quién la presenta y el canal; exige motivo y muestra el plazo (RN-M6)", async () => {
    const registrar = vi.spyOn(api, "registrarSolicitudTitular").mockResolvedValue(PENDIENTE);
    render(<AppRouter rutaInicial="/pacientes/4" rolInicial="auditor_clinico" />);
    const seccion = await screen.findByTestId("solicitudes-titular");
    expect(seccion).toHaveTextContent(/sin solicitudes/i);
    await userEvent.click(within(seccion).getByRole("button", { name: /registrar solicitud/i }));
    const formulario = screen.getByTestId("registro-solicitud");
    const boton = within(formulario).getByRole("button", { name: /^registrar$/i });
    expect(within(formulario).getByLabelText(/documento cuya decisión/i)).toHaveValue("REC-2");
    expect(boton).toBeDisabled();
    await userEvent.selectOptions(within(formulario).getByLabelText(/quién la presenta/i), "representante");
    await userEvent.selectOptions(within(formulario).getByLabelText(/^canal/i), "escrito");
    await userEvent.type(within(formulario).getByLabelText(/motivo del titular/i), "no está de acuerdo con la prioridad");
    await userEvent.click(boton);
    await waitFor(() => expect(registrar).toHaveBeenCalledWith(4, { documento_id: "REC-2", presentada_por: "representante", canal: "escrito", motivo: "no está de acuerdo con la prioridad" }));
    const fila = await screen.findByTestId("solicitud-titular");
    expect(fila).toHaveTextContent("Pendiente");
    expect(fila).toHaveTextContent(/presentada por su representante por escrito/i);
    expect(fila).toHaveTextContent(/plazo para responder/i);
    expect(screen.getByText(/solicitud registrada\. hay plazo hasta/i)).toBeInTheDocument();
  }, 15_000);
});

describe("responder la solicitud", () => {
  it("la respuesta exige texto, dice si la decisión se mantiene o se corrigió y queda firmada", async () => {
    vi.spyOn(api, "obtenerPaciente").mockResolvedValue({ ...FICHA, solicitudes: [PENDIENTE] } as never);
    const responder = vi.spyOn(api, "responderSolicitudTitular").mockResolvedValue({
      ...PENDIENTE, estado: "respondida", resultado: "corregida", respuesta: "se bajó la prioridad tras revisar el original", respondida_por: "aud.ana", respondida_en: AHORA,
    });
    render(<AppRouter rutaInicial="/pacientes/4" rolInicial="auditor_clinico" />);
    const fila = await screen.findByTestId("solicitud-titular");
    await userEvent.click(within(fila).getByRole("button", { name: /responder/i }));
    const formulario = screen.getByTestId("respuesta-solicitud");
    const guardar = within(formulario).getByRole("button", { name: /guardar respuesta/i });
    expect(guardar).toBeDisabled();
    await userEvent.selectOptions(within(formulario).getByLabelText(/resultado de la revisión/i), "corregida");
    await userEvent.type(within(formulario).getByLabelText(/respuesta al titular/i), "se bajó la prioridad tras revisar el original");
    await userEvent.click(guardar);
    await waitFor(() => expect(responder).toHaveBeenCalledWith(7, { resultado: "corregida", respuesta: "se bajó la prioridad tras revisar el original" }));
    expect(fila).toHaveTextContent("Decisión corregida");
    expect(fila).toHaveTextContent(/respondió aud\.ana/i);
    expect(within(fila).queryByRole("button", { name: /responder/i })).not.toBeInTheDocument();
  }, 15_000);
});

describe("dónde se ven las pendientes", () => {
  it("el directorio las lista arriba con el plazo y marca las vencidas", async () => {
    vi.spyOn(api, "listarSolicitudesTitular").mockResolvedValue([PENDIENTE, { ...PENDIENTE, id: 8, documento_id: "EPI-1", vence_en: AYER }]);
    render(<AppRouter rutaInicial="/pacientes" rolInicial="auditor_clinico" />);
    const aviso = await screen.findByTestId("solicitudes-pendientes");
    expect(aviso).toHaveTextContent("2 solicitudes del titular sin responder");
    expect(aviso).toHaveTextContent("Vencida");
    expect(within(aviso).getAllByRole("link", { name: "Ana María Pérez" })[0]).toHaveAttribute("href", "/pacientes/4");
  });

  it("al abrir el documento, el revisor ve la solicitud y un enlace para responder en la ficha", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(detalleCaso1({ paciente_id: 4, solicitud_titular: PENDIENTE }));
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="auditor_clinico" />);
    const aviso = await screen.findByTestId("aviso-titular");
    expect(aviso).toHaveTextContent(/revisión pedida por su representante/i);
    expect(aviso).toHaveTextContent("«no está de acuerdo con la prioridad»");
    expect(within(aviso).getByRole("link", { name: /responder en la ficha/i })).toHaveAttribute("href", "/pacientes/4");
  });
});
