/**
 * Directorio de pacientes (RN-M6): localizar lo asociado a una persona, corregir un dato con rastro (RN-G4)
 * y no mostrarlo a quien no ve datos clínicos (RN-K2).
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";

const AHORA = new Date().toISOString();
const ANA = { id: 4, pais: "CO", tipo_documento: "CC", numero_documento: "41234567", nombre: "Ana Maria Peres", edad: 58, sexo: "F", documentos: 2, creado_en: AHORA, actualizado_en: AHORA };
const LUIS = { id: 5, pais: "CO", tipo_documento: "CC", numero_documento: "79456123", nombre: "Luis Castro", edad: 49, sexo: null, documentos: 1, creado_en: AHORA, actualizado_en: AHORA };
const FICHA = {
  ...ANA,
  historial: [],
  documentos_listado: [
    { documento_id: "REC-2", version: 1, estado: "ENRUTADO", nivel_prioridad: "Rutina", tipo: "Receta Médica", fecha_documento: "03/04/2026", creado_en: AHORA },
    { documento_id: "EPI-1", version: 2, estado: "ENTREGADO", nivel_prioridad: "Crítico", tipo: "Epicrisis o Alta", fecha_documento: null, creado_en: AHORA },
  ],
};

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "obtenerResumen").mockResolvedValue({ total: 3, por_estado: {}, por_prioridad: {}, en_revision: 0, alertas_sin_acuse: 0, recetas_por_verificar: 0, ordenes_por_autorizar: 0, enrutados: 0, entregados_hoy: 0 });
  vi.spyOn(api, "listarPacientes").mockResolvedValue({ items: [ANA, LUIS], total: 2, limit: 20, offset: 0 } as never);
  vi.spyOn(api, "obtenerPaciente").mockResolvedValue(FICHA as never);
});
afterEach(() => vi.restoreAllMocks());

describe("Directorio de pacientes (RN-M6)", () => {
  it("lista los pacientes con su identificación y busca por nombre o documento", async () => {
    render(<AppRouter rutaInicial="/pacientes" rolInicial="auditor_clinico" />);
    const filas = await screen.findAllByTestId("fila-paciente");
    expect(filas).toHaveLength(2);
    expect(filas[0]).toHaveTextContent("Ana Maria Peres");
    expect(filas[0]).toHaveTextContent("CC 41234567");
    expect(filas[0]).toHaveTextContent("58 años");
    expect(screen.getByRole("link", { name: "Pacientes" })).toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox", { name: /buscar/i }), "castro{Enter}");
    await waitFor(() => expect(api.listarPacientes).toHaveBeenLastCalledWith({ q: "castro", limit: 20, offset: 0 }));
  });

  it("explica el directorio vacío en vez de mostrar una tabla en blanco", async () => {
    vi.spyOn(api, "listarPacientes").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 } as never);
    render(<AppRouter rutaInicial="/pacientes" rolInicial="auditor_clinico" />);
    expect(await screen.findByText(/todavía no hay pacientes/i)).toBeInTheDocument();
  });

  it("la ficha muestra los documentos del paciente con enlace a cada uno", async () => {
    render(<AppRouter rutaInicial="/pacientes/4" rolInicial="auditor_clinico" />);
    expect(await screen.findByRole("heading", { level: 1, name: "Ana Maria Peres" })).toBeInTheDocument();
    const documentos = screen.getAllByTestId("documento-de-paciente");
    expect(documentos).toHaveLength(2);
    expect(documentos[0]).toHaveTextContent("REC-2");
    expect(documentos[0]).toHaveTextContent("Receta médica");
    expect(within(documentos[0]).getByRole("link", { name: /abrir/i })).toHaveAttribute("href", "/documentos/REC-2");
    expect(documentos[1]).toHaveTextContent("versión 2");
    expect(screen.getByTestId("historial-paciente")).toHaveTextContent(/sin correcciones/i);
  });

  it("corregir un dato exige usuario y motivo, y deja el cambio en el historial (RN-G4)", async () => {
    const corregido = { ...ANA, nombre: "Ana María Pérez", historial: [{ fecha_hora: AHORA, usuario: "aud.ana", motivo: "apellido mal digitado", anterior: { nombre: "Ana Maria Peres" }, nuevo: { nombre: "Ana María Pérez" } }] };
    const editar = vi.spyOn(api, "editarPaciente").mockResolvedValue(corregido as never);
    render(<AppRouter rutaInicial="/pacientes/4" rolInicial="auditor_clinico" />);
    await userEvent.click(await screen.findByRole("button", { name: /corregir datos/i }));
    const formulario = screen.getByTestId("edicion-paciente");
    const guardar = within(formulario).getByRole("button", { name: /guardar corrección/i });
    const nombre = within(formulario).getByLabelText("Nombre");
    await userEvent.clear(nombre);
    await userEvent.type(nombre, "Ana María Pérez");
    expect(guardar).toBeDisabled();
    expect(formulario).toHaveTextContent(/escribe tu usuario/i);
    await userEvent.type(screen.getByLabelText(/firmo como/i), "aud.ana");
    expect(formulario).toHaveTextContent(/falta el motivo/i);
    await userEvent.type(within(formulario).getByLabelText(/motivo de la corrección/i), "apellido mal digitado");
    await userEvent.click(guardar);
    await waitFor(() => expect(editar).toHaveBeenCalledWith(4, { nombre: "Ana María Pérez", usuario: "aud.ana", rol: "auditor_clinico", motivo: "apellido mal digitado" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Ana María Pérez" })).toBeInTheDocument();
    expect(screen.getByTestId("historial-paciente")).toHaveTextContent("apellido mal digitado");
    expect(screen.getByTestId("historial-paciente")).toHaveTextContent("Ana Maria Peres → Ana María Pérez");
  }, 15_000);

  it("quien no ve datos clínicos no entra al directorio (RN-K2)", async () => {
    render(<AppRouter rutaInicial="/pacientes" rolInicial="gestor" />);
    expect(await screen.findByRole("heading", { name: /sin acceso para este rol/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Pacientes" })).toBeNull();
    expect(api.listarPacientes).not.toHaveBeenCalled();
  });
});
