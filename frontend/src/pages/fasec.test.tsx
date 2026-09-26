import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";

const RECETAS = [
  { documento_id: "REC-2", version: 1, nivel_prioridad: "Rutina", creado_en: new Date(Date.now() - 20 * 60000).toISOString(),
    medicamentos: [{ dci: "apixaban", dosis: "5 mg", dosis_valor: "5", via: "oral", frecuencia: "cada 12 h", alto_riesgo: true, control_especial: false }],
    alto_riesgo: true, control_especial: false, verificaciones_requeridas: 2, verificaciones: [{ orden: 1, usuario: "qf.maria" }], motivo_destino: "alto_riesgo", fecha_documento: "03/04/2026" },
  { documento_id: "REC-1", version: 1, nivel_prioridad: "Rutina", creado_en: new Date(Date.now() - 50 * 60000).toISOString(),
    medicamentos: [{ dci: "losartan", dosis: "50 mg", dosis_valor: "50", via: "oral", frecuencia: "cada 24 h", alto_riesgo: false, control_especial: false }],
    alto_riesgo: false, control_especial: false, verificaciones_requeridas: 1, verificaciones: [], motivo_destino: null, fecha_documento: "03/04/2026" },
];

const BANDEJA = {
  por_autorizar: [
    { documento_id: "ORD-AMB", version: 1, nivel_prioridad: "Rutina", canal_origen: "Consulta_Ambulatoria", creado_en: new Date().toISOString(), cobertura: "contributivo",
      motivo_destino: "solicitud_autorizacion_eps", documentacion_incompleta: false, procedimientos: ["Cateterismo cardíaco"], cups: ["372100"], diagnosticos: ["Angina estable I20.8"], justificacion: "RN-E2: orden ambulatoria a Auditoría", fecha_documento: "03/04/2026" },
    { documento_id: "ORD-INC", version: 1, nivel_prioridad: "Rutina", canal_origen: "Consulta_Ambulatoria", creado_en: new Date().toISOString(), cobertura: "contributivo",
      motivo_destino: "documentacion_incompleta", documentacion_incompleta: true, procedimientos: ["Ecocardiograma de estrés"], cups: [], diagnosticos: ["Angina estable I20.8"], justificacion: "RN-E5: documentacion_incompleta, vuelve al solicitante (faltan justificacion_clinica, cups)", fecha_documento: "03/04/2026" },
  ],
  avisos_urgencias: [
    { documento_id: "ORD-URG", version: 1, nivel_prioridad: "Urgente", canal_origen: "Guardia_Emergencias", creado_en: new Date().toISOString(), cobertura: null,
      motivo_destino: "informe_atencion_inicial_urgencias", documentacion_incompleta: false, procedimientos: ["Cateterismo cardíaco"], cups: ["372100"], diagnosticos: ["SCA I21.4"], justificacion: "RN-CO13", fecha_documento: "03/04/2026" },
  ],
};

const RESUMEN = { total: 51, por_estado: { EN_REVISION_HUMANA: 48, ENRUTADO: 2, ENTREGADO: 1 }, por_prioridad: { "Crítico": 15, Rutina: 36 },
  en_revision: 48, alertas_sin_acuse: 15, recetas_por_verificar: 2, ordenes_por_autorizar: 2, enrutados: 2, entregados_hoy: 1 };

const ENRUTADOS = { items: [
  { documento_id: "DOC-ENR", version: 1, estado: "ENRUTADO", nivel_prioridad: "Crítico", tipo_contenido: "texto", formato: "txt", nombre_archivo: null, canal_origen: "Guardia_Emergencias", creado_en: new Date().toISOString(), tipo: "Informe de Imágenes", motivo_auditoria: null, codigo_error: null, num_paginas: 1 },
], total: 1, limit: 20, offset: 0 };

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarDocumentos").mockResolvedValue(ENRUTADOS as never);
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "colaFarmacia").mockResolvedValue(RECETAS as never);
  vi.spyOn(api, "bandejaAutorizaciones").mockResolvedValue(BANDEJA as never);
  vi.spyOn(api, "obtenerResumen").mockResolvedValue(RESUMEN as never);
});
afterEach(() => vi.restoreAllMocks());

describe("Farmacia (RN-E6, RN-J6)", () => {
  it("lista recetas con sus marcas y bloquea la segunda verificación a la misma persona", async () => {
    const verificar = vi.spyOn(api, "verificarReceta").mockResolvedValue({ documento_id: "REC-2", verificaciones: [{ orden: 1, usuario: "qf.maria" }, { orden: 2, usuario: "qf.pedro" }], requeridas: 2, completa: true, estado: "ENTREGADO", pendientes: [] });
    render(<AppRouter rutaInicial="/farmacia" rolInicial="quimico_farmaceutico" />);
    const filas = await screen.findAllByTestId("fila-receta");
    expect(filas).toHaveLength(2);
    expect(filas[0]).toHaveTextContent("apixaban");
    expect(filas[0]).toHaveTextContent(/alto riesgo/i);
    expect(filas[0]).toHaveTextContent("1 de 2");
    // la misma persona que hizo la primera no puede hacer la segunda
    await userEvent.type(screen.getByLabelText(/^usuario/i), "qf.maria");
    const boton = within(filas[0]).getByRole("button", { name: /segunda verificación/i });
    expect(boton).toBeDisabled();
    expect(filas[0]).toHaveTextContent(/requiere otra persona/i);
    // otra persona sí
    await userEvent.clear(screen.getByLabelText(/^usuario/i));
    await userEvent.type(screen.getByLabelText(/^usuario/i), "qf.pedro");
    await userEvent.click(within(filas[0]).getByRole("button", { name: /segunda verificación/i }));
    await waitFor(() => expect(verificar).toHaveBeenCalledWith("REC-2", "qf.pedro"));
    expect(await screen.findByRole("status")).toHaveTextContent(/REC-2.*verificada/i);
    expect(filas[1]).toHaveTextContent("0 de 1");
    expect(within(filas[1]).getByRole("button", { name: /primera verificación/i })).toBeInTheDocument();
  });
});

describe("Autorizaciones (RN-E5, RN-E9, RN-CO13)", () => {
  it("separa por autorizar de avisos de urgencias y devolver exige motivo", async () => {
    const resolver = vi.spyOn(api, "resolverAutorizacion").mockResolvedValue({ documento_id: "ORD-INC", autorizacion: { estado: "devuelta", usuario: "aut.luis", motivo: "falta", fecha_hora: "" }, estado: "ENTREGADO", pendientes: [] });
    render(<AppRouter rutaInicial="/autorizaciones" rolInicial="auditor_autorizaciones" />);
    const filas = await screen.findAllByTestId("fila-orden");
    expect(filas).toHaveLength(2);
    expect(filas[1]).toHaveTextContent(/documentación incompleta/i);
    expect(filas[0]).toHaveTextContent("372100");
    await userEvent.click(screen.getByRole("tab", { name: /avisos de urgencias/i }));
    const avisos = await screen.findAllByTestId("fila-aviso");
    expect(avisos[0]).toHaveTextContent("ORD-URG");
    expect(avisos[0]).toHaveTextContent(/sin autorización previa/i);
    await userEvent.click(screen.getByRole("tab", { name: /por autorizar/i }));
    await userEvent.type(screen.getByLabelText(/^usuario/i), "aut.luis");
    const filaInc = (await screen.findAllByTestId("fila-orden"))[1];
    expect(within(filaInc).getByRole("button", { name: /devolver/i })).toBeDisabled();
    await userEvent.type(within(filaInc).getByLabelText(/motivo/i), "falta justificación clínica");
    await userEvent.click(within(filaInc).getByRole("button", { name: /devolver/i }));
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("ORD-INC", { accion: "devolver", usuario: "aut.luis", motivo: "falta justificación clínica" }));
  });
});

describe("Entregas e inicio", () => {
  it("la página de entregas lista lo enrutado y confirma destinos", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue({
      documento_id: "DOC-ENR", version: 1, estado: "ENRUTADO", nivel_prioridad: "Crítico", status_backup: "ok", ruta_storage: null, posible_duplicado_de: null, codigo_error: null, entregas: {},
      resultado: { enrutamiento: { destino_principal: "Cola_Emergencia_Medica", destinos_secundarios: ["Historia_Clinica_Electronica"], entregas_retenidas: { Historia_Clinica_Electronica: "identidad_ausente_conciliar" }, motivos_destino: {}, destinos_tras_revision: [], documentacion_incompleta: false, justificacion_enrutamiento: "" } },
    } as never);
    const confirmar = vi.spyOn(api, "confirmarEntrega").mockResolvedValue({ documento_id: "DOC-ENR", estado: "ENRUTADO", entregas: { Cola_Emergencia_Medica: true }, retenidas: {}, pendientes: ["acuse_alerta"] });
    render(<AppRouter rutaInicial="/entregas" rolInicial="auditor_clinico" />);
    const fila = await screen.findByTestId("fila-entrega");
    expect(fila).toHaveTextContent("DOC-ENR");
    await userEvent.click(within(fila).getByRole("button", { name: /confirmar Cola_Emergencia_Medica/i }));
    await waitFor(() => expect(confirmar).toHaveBeenCalledWith("DOC-ENR", "Cola_Emergencia_Medica"));
    expect(fila).toHaveTextContent(/retenida/i);
  });

  it("el inicio muestra los contadores del resumen y accesos según el rol", async () => {
    render(<AppRouter rutaInicial="/inicio" rolInicial="quimico_farmaceutico" />);
    expect(await screen.findByTestId("contador-recetas")).toHaveTextContent("2");
    expect(screen.getByTestId("contador-alertas")).toHaveTextContent("15");
    expect(screen.getByRole("link", { name: /ir a farmacia/i })).toHaveAttribute("href", "/farmacia");
    expect(screen.queryByRole("link", { name: /ir a la cola de revisión/i })).not.toBeInTheDocument();
  });
});
