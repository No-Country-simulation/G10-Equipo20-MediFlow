import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";
import { detalleCaso1, resultadoCaso1 } from "../test/fixtures";
import type { DocumentoDetalle } from "../types";

const COLA = [
  { documento_id: "DOC-ANTES", version: 1, nivel_prioridad: "Crítico", motivo_auditoria: "critico_baja_confianza", campos_dudosos: [], tipo: "Informe de Imágenes", creado_en: new Date(Date.now() - 6 * 60000).toISOString(), plazo_minutos: 15 },
  { documento_id: "DOC-CLIN-2026-8942", version: 1, nivel_prioridad: "Crítico", motivo_auditoria: "critico_baja_confianza", campos_dudosos: ["diagnostico_codigo"], tipo: "Informe de Imágenes", creado_en: new Date(Date.now() - 4 * 60000).toISOString(), plazo_minutos: 15 },
  { documento_id: "DOC-DESPUES", version: 1, nivel_prioridad: "Rutina", motivo_auditoria: "campo_dudoso", campos_dudosos: ["profesional"], tipo: "Receta Médica", creado_en: new Date(Date.now() - 2 * 60000).toISOString(), plazo_minutos: 1440 },
];

function enRevision(): DocumentoDetalle {
  const resultado = resultadoCaso1({
    estado: "EN_REVISION_HUMANA",
    evaluacion: { requiere_auditoria_humana: true, motivo_auditoria: "critico_baja_confianza", campos_dudosos: ["diagnostico_codigo"] },
    enrutamiento: {
      ...resultadoCaso1().enrutamiento,
      destino_principal: "Cola_Revision_Humana",
      destinos_secundarios: [],
      destinos_tras_revision: ["Cola_Emergencia_Medica", "Historia_Clinica_Electronica"],
    },
  });
  return detalleCaso1({
    estado: "EN_REVISION_HUMANA",
    formato: "pdf",
    num_paginas: 2,
    nombre_archivo: "cardio_mixed.pdf",
    resultado,
    confianzas: { identidad_paciente: 0.96, medicamento_dosis: null, diagnostico_codigo: 0.6, profesional: 0.9 },
    umbrales: { clasificacion: 0.85, identidad_paciente: 0.95, medicamento_dosis: 0.95, diagnostico_codigo: 0.9, profesional: 0.85, resto: 0.8 },
    texto_enviado_llm: "Paciente: [PACIENTE_1], 52 años. TC de tórax: tromboembolismo pulmonar agudo.",
  });
}

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue(COLA as never);
  vi.spyOn(api, "consultarDocumento").mockResolvedValue(enRevision());
});
afterEach(() => vi.restoreAllMocks());

const RUTA = "/documentos/DOC-CLIN-2026-8942";

describe("banco de trabajo: tres paneles", () => {
  it("muestra original, extracción con confianza por campo y decisión con línea de tiempo", async () => {
    render(<AppRouter rutaInicial={RUTA} rolInicial="auditor_clinico" />);
    expect(await screen.findByRole("heading", { name: /^original/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^extracción/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^decisión/i })).toBeInTheDocument();
    // original: vista previa de la página 1 y navegación
    expect(screen.getByRole("img", { name: /página 1/i })).toHaveAttribute("src", "/api/documentos/DOC-CLIN-2026-8942/vista_previa?pagina=1");
    // extracción: el auditor clínico ve el nombre; el diagnóstico está bajo el umbral
    expect(screen.getByText("Carlos Eduardo Mendes")).toBeInTheDocument();
    const dx = screen.getByTestId("campo-diagnostico_codigo");
    expect(dx).toHaveTextContent("0.60");
    expect(dx).toHaveTextContent(/bajo el umbral 0.90/i);
    expect(within(dx).getByRole("button", { name: /corregir/i })).toBeInTheDocument();
    expect(screen.getByTestId("campo-identidad_paciente")).toHaveTextContent("0.96");
    expect(screen.getAllByText("Tromboembolismo pulmonar agudo").length).toBeGreaterThanOrEqual(1);  // en el encabezado y en la extracción
    expect(screen.getByText(/NEWS2 total/)).toHaveTextContent("10");
    // reglas y línea de tiempo
    expect(screen.getByText("RN-D2")).toBeInTheDocument();
    expect(screen.getAllByTestId("evento").length).toBeGreaterThanOrEqual(6);
    // rastro de privacidad
    expect(screen.getByText(/qué salió al llm/i)).toBeInTheDocument();
  });

  it("el modo discreto enmascara nombre y documento del paciente y viene activo para el jefe de urgencias", async () => {
    render(<AppRouter rutaInicial={RUTA} rolInicial="jefe_urgencias" />);
    await screen.findByRole("heading", { name: /^original/i });
    expect(screen.queryByText("Carlos Eduardo Mendes")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/modo discreto/i)).toBeChecked();
    await userEvent.click(screen.getByLabelText(/modo discreto/i));
    expect(await screen.findByText("Carlos Eduardo Mendes")).toBeInTheDocument();
  });

  it("aprobar envía usuario y rol y recarga el documento (RN-J3, RN-G4)", async () => {
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", resultado: resultadoCaso1() });
    render(<AppRouter rutaInicial={RUTA} rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /^decisión/i });
    const aprobar = screen.getByRole("button", { name: /^aprobar/i });
    expect(aprobar).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/firmo como/i), "ana.auditora");
    await userEvent.click(aprobar);
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({ accion: "aprobar", usuario: "ana.auditora", rol: "auditor_clinico" })));
    await waitFor(() => expect(api.consultarDocumento).toHaveBeenCalledTimes(2));
  });

  it("corregir un campo dudoso manda la ruta del campo y el valor nuevo (RN-J4, RN-J8)", async () => {
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", resultado: resultadoCaso1() });
    render(<AppRouter rutaInicial={RUTA} rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /^decisión/i });
    await userEvent.type(screen.getByLabelText(/firmo como/i), "ana");
    await userEvent.click(within(screen.getByTestId("campo-diagnostico_codigo")).getByRole("button", { name: /corregir/i }));
    const valor = screen.getByLabelText(/valor corregido/i);
    expect(screen.getByLabelText(/campo a corregir/i)).toHaveValue("extraccion.diagnosticos[0].cie10_sugerido");
    await userEvent.clear(valor);
    await userEvent.type(valor, "I26.0");
    await userEvent.type(screen.getByLabelText(/^motivo/i), "código confirmado en el informe");
    await userEvent.click(screen.getByRole("button", { name: /aplicar corrección/i }));
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({
      accion: "corregir", correcciones: { "extraccion.diagnosticos[0].cie10_sugerido": "I26.0" },
    })));
  });

  it("rechazar exige motivo y los atajos A y R respetan esa regla (RN-J3)", async () => {
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "RECHAZADO", resultado: resultadoCaso1() });
    render(<AppRouter rutaInicial={RUTA} rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /^decisión/i });
    await userEvent.type(screen.getByLabelText(/firmo como/i), "ana");
    expect(screen.getByRole("button", { name: /^rechazar/i })).toBeDisabled();
    fireEvent.keyDown(document.body, { key: "r" });
    expect(resolver).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText(/^motivo/i), "documento de otra institución");
    fireEvent.keyDown(document.body, { key: "r" });
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({ accion: "rechazar", motivo: "documento de otra institución" })));
  });

  it("el atajo A aprueba cuando hay usuario", async () => {
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", resultado: resultadoCaso1() });
    render(<AppRouter rutaInicial={RUTA} rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /^decisión/i });
    await userEvent.type(screen.getByLabelText(/firmo como/i), "ana");
    fireEvent.keyDown(document.body, { key: "a" });
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({ accion: "aprobar" })));
  });

  it("desde la cola, J y K navegan al siguiente y al anterior (RN-J1)", async () => {
    render(<AppRouter rutaInicial={`${RUTA}?cola=1`} rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /^decisión/i });
    expect(screen.getByText(/2 de 3 en la cola/i)).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: "j" });
    await waitFor(() => expect(api.consultarDocumento).toHaveBeenLastCalledWith("DOC-DESPUES"));
    fireEvent.keyDown(document.body, { key: "k" });
    await waitFor(() => expect(api.consultarDocumento).toHaveBeenLastCalledWith("DOC-CLIN-2026-8942"));
  });

  it("la alerta pendiente se muestra en el encabezado con acuse en línea (RN-J7, RN-Q5)", async () => {
    const acusar = vi.spyOn(api, "acusarAlerta").mockResolvedValue({ estado_acuse: "acusado", acusado_por: "jefe", estado: "EN_REVISION_HUMANA" });
    render(<AppRouter rutaInicial={RUTA} rolInicial="jefe_urgencias" />);
    const alerta = await screen.findByTestId("alerta-documento");
    expect(alerta).toHaveTextContent(/restantes|vencido/);
    expect(alerta).not.toHaveTextContent("Mendes");
    await userEvent.click(within(alerta).getByRole("button", { name: /dar acuse/i }));
    await userEvent.type(within(alerta).getByLabelText(/quién da el acuse/i), "jefe.urgencias");
    await userEvent.click(within(alerta).getByRole("button", { name: /confirmar acuse/i }));
    await waitFor(() => expect(acusar).toHaveBeenCalledWith("DOC-CLIN-2026-8942", "jefe.urgencias"));
  });

  it("un documento enrutado muestra el plan de entrega y confirma destinos", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(detalleCaso1({ formato: "pdf" }));
    const confirmar = vi.spyOn(api, "confirmarEntrega").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", entregas: { Cola_Emergencia_Medica: true }, retenidas: { Historia_Clinica_Electronica: "identidad_ausente_conciliar" }, pendientes: ["acuse_alerta"] });
    render(<AppRouter rutaInicial={RUTA} rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /^decisión/i });
    expect(screen.getByText(/identidad_ausente_conciliar/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /confirmar Cola_Emergencia_Medica/i }));
    await waitFor(() => expect(confirmar).toHaveBeenCalledWith("DOC-CLIN-2026-8942", "Cola_Emergencia_Medica"));
    expect(await screen.findByText(/acuse_alerta/)).toBeInTheDocument();
  });

  it("un documento de texto muestra el original como texto", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(detalleCaso1({ formato: "txt", tipo_contenido: "texto" }));
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, text: () => Promise.resolve("TC de tórax: tromboembolismo pulmonar agudo bilateral.") } as Response);
    render(<AppRouter rutaInicial={RUTA} rolInicial="auditor_clinico" />);
    expect(await screen.findByText(/tromboembolismo pulmonar agudo bilateral/)).toBeInTheDocument();
  });
});

describe("cola de revisión", () => {
  it("lista la cola con prioridad, motivo y plazo, y abre el banco de trabajo con navegación de cola", async () => {
    render(<AppRouter rutaInicial="/revision" rolInicial="auditor_clinico" />);
    const filas = await screen.findAllByTestId("fila-cola");
    expect(filas).toHaveLength(3);
    expect(filas[0]).toHaveTextContent("DOC-ANTES");
    expect(filas[0]).toHaveTextContent(/Crítico con baja confianza/);
    expect(filas[0]).toHaveTextContent(/restantes|vencido/);
    expect(within(filas[0]).getByRole("link", { name: /revisar/i })).toHaveAttribute("href", "/documentos/DOC-ANTES?cola=1");
  });
});
