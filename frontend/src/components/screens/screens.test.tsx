import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api";
import { COLA, detalleCaso1, resultadoCaso1 } from "../../test/fixtures";
import { PrioridadBadge } from "../PrioridadBadge";
import { AlertaCriticaScreen } from "./AlertaCriticaScreen";
import { CockpitScreen } from "./CockpitScreen";
import { EntregaScreen } from "./EntregaScreen";
import { IngestaScreen } from "./IngestaScreen";
import { ProcesamientoScreen } from "./ProcesamientoScreen";
import { RevisionHumanaScreen } from "./RevisionHumanaScreen";

afterEach(() => vi.restoreAllMocks());

describe("PrioridadBadge", () => {
  it.each([
    ["Crítico", "prioridad-critico"],
    ["Urgente", "prioridad-urgente"],
    ["Rutina", "prioridad-rutina"],
  ] as const)("muestra %s con su clase", (nivel, clase) => {
    render(<PrioridadBadge nivel={nivel} />);
    expect(screen.getByText(nivel)).toHaveClass(clase);
  });
});

describe("IngestaScreen", () => {
  it("no permite enviar sin documento_id ni texto", () => {
    render(<IngestaScreen onEnviado={() => {}} />);
    expect(screen.getByRole("button", { name: /enviar al agente/i })).toBeDisabled();
  });

  it("carga un caso sintético y lo envía con canal y cobertura", async () => {
    const enviar = vi.spyOn(api, "enviarDocumento").mockResolvedValue(detalleCaso1());
    const onEnviado = vi.fn();
    render(<IngestaScreen onEnviado={onEnviado} />);
    await userEvent.click(screen.getByRole("button", { name: /TEP Masivo C1/i }));
    expect(screen.getByLabelText(/documento_id/i)).toHaveValue("DOC-CLIN-2026-8942");
    await userEvent.click(screen.getByRole("button", { name: /enviar al agente/i }));
    await waitFor(() => expect(onEnviado).toHaveBeenCalledWith(detalleCaso1()));
    expect(enviar.mock.calls[0][0]).toMatchObject({ canal_origen: "Guardia_Emergencias", tipo_contenido: "texto" });
  });

  it("muestra el código de error cuando el backend rechaza (RN-A1)", async () => {
    vi.spyOn(api, "enviarDocumento").mockResolvedValue({ ...detalleCaso1(), estado: "RECHAZADO", codigo_error: "tamano_excedido", resultado: null });
    render(<IngestaScreen onEnviado={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /TEP Masivo C1/i }));
    await userEvent.click(screen.getByRole("button", { name: /enviar al agente/i }));
    expect(await screen.findByText(/tamano_excedido/)).toBeInTheDocument();
  });
});

describe("ProcesamientoScreen", () => {
  it("muestra las transiciones del ciclo de vida en orden (RN-I3)", () => {
    render(<ProcesamientoScreen detalle={detalleCaso1()} onContinuar={() => {}} />);
    const estados = screen.getAllByTestId("transicion").map((e) => e.textContent);
    expect(estados[0]).toContain("RECIBIDO");
    expect(estados[estados.length - 1]).toContain("ENRUTADO");
    expect(estados).toHaveLength(6);
  });
});

describe("CockpitScreen", () => {
  it("muestra prioridad, hallazgos, NEWS2, destinos y el historial de reglas (RN-G2)", () => {
    render(<CockpitScreen detalle={detalleCaso1()} onContinuar={() => {}} />);
    expect(screen.getByText("Crítico")).toBeInTheDocument();
    expect(screen.getByText("TEP_AGUDO")).toBeInTheDocument();
    expect(screen.getByText(/NEWS2/)).toHaveTextContent("10");
    expect(screen.getByText("Cola_Emergencia_Medica")).toBeInTheDocument();
    expect(screen.getByText("RN-D2")).toBeInTheDocument();
    expect(screen.getByText(/retenida/i)).toBeInTheDocument();
  });

  it("señala la revisión humana con su motivo (RN-E8)", () => {
    const resultado = resultadoCaso1({
      evaluacion: { requiere_auditoria_humana: true, motivo_auditoria: "critico_baja_confianza", campos_dudosos: ["diagnostico_codigo"] },
      estado: "EN_REVISION_HUMANA",
    });
    render(<CockpitScreen detalle={detalleCaso1({ estado: "EN_REVISION_HUMANA", resultado })} onContinuar={() => {}} />);
    expect(screen.getByText(/critico_baja_confianza/)).toBeInTheDocument();
  });
});

describe("AlertaCriticaScreen", () => {
  it("muestra el mensaje sin datos del paciente y exige usuario para el acuse (RN-Q4, RN-Q5)", async () => {
    const acusar = vi.spyOn(api, "acusarAlerta").mockResolvedValue({ estado_acuse: "acusado", acusado_por: "jefe", estado: "ENRUTADO" });
    render(<AlertaCriticaScreen detalle={detalleCaso1()} onAcusada={() => {}} />);
    expect(screen.getByText(/Alerta Crítica\. Doc: DOC-CLIN-2026-8942/)).toBeInTheDocument();
    expect(screen.queryByText(/Mendes/)).not.toBeInTheDocument();
    const boton = screen.getByRole("button", { name: /dar acuse/i });
    expect(boton).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/usuario/i), "jefe.urgencias");
    await userEvent.click(boton);
    await waitFor(() => expect(acusar).toHaveBeenCalledWith("DOC-CLIN-2026-8942", "jefe.urgencias"));
  });
});

describe("RevisionHumanaScreen", () => {
  it("lista la cola en el orden del backend con su plazo (RN-J1, RN-J2)", async () => {
    vi.spyOn(api, "colaRevision").mockResolvedValue(COLA);
    render(<RevisionHumanaScreen documentoInicial={null} onResuelto={() => {}} />);
    const filas = await screen.findAllByTestId("item-cola");
    expect(filas[0]).toHaveTextContent("DOC-CRIT");
    expect(filas[0]).toHaveTextContent("15 min");
    expect(filas[1]).toHaveTextContent("DOC-RUT-1");
  });

  it("rechazar exige motivo y aprobar envía usuario y rol (RN-J3, RN-G4)", async () => {
    vi.spyOn(api, "colaRevision").mockResolvedValue(COLA);
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CRIT", estado: "ENRUTADO", resultado: resultadoCaso1() });
    render(<RevisionHumanaScreen documentoInicial="DOC-CRIT" onResuelto={() => {}} />);
    await screen.findAllByTestId("item-cola");
    await userEvent.type(screen.getByLabelText(/usuario/i), "ana");
    expect(screen.getByRole("button", { name: /rechazar/i })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /aprobar/i }));
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CRIT", expect.objectContaining({ accion: "aprobar", usuario: "ana", rol: "auditor_clinico" })));
  });
});

describe("EntregaScreen", () => {
  it("muestra el plan, marca la HCE retenida y confirma destinos (RN-A4, RN-J7)", async () => {
    const confirmar = vi.spyOn(api, "confirmarEntrega").mockResolvedValue({
      documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", entregas: { Cola_Emergencia_Medica: true },
      retenidas: { Historia_Clinica_Electronica: "identidad_ausente_conciliar" }, pendientes: ["acuse_alerta"],
    });
    render(<EntregaScreen detalle={detalleCaso1()} onReiniciar={() => {}} />);
    expect(screen.getByText(/identidad_ausente_conciliar/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /confirmar Cola_Emergencia_Medica/i }));
    await waitFor(() => expect(confirmar).toHaveBeenCalledWith("DOC-CLIN-2026-8942", "Cola_Emergencia_Medica"));
    expect(await screen.findByText(/acuse_alerta/)).toBeInTheDocument();
  });
});

describe("IngestaScreen con archivo (PDF, PNG, JPG)", () => {
  it("envía el archivo seleccionado por multipart en vez del texto", async () => {
    const enviarArchivo = vi.spyOn(api, "enviarArchivo").mockResolvedValue(detalleCaso1());
    const onEnviado = vi.fn();
    render(<IngestaScreen onEnviado={onEnviado} />);
    await userEvent.type(screen.getByLabelText(/documento_id/i), "DOC-PDF-1");
    const archivo = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "informe.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByLabelText(/archivo/i), archivo);
    expect(screen.getByText(/informe\.pdf/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /enviar al agente/i }));
    await waitFor(() => expect(enviarArchivo).toHaveBeenCalled());
    expect(enviarArchivo.mock.calls[0][1]).toMatchObject({ documento_id: "DOC-PDF-1" });
    expect(onEnviado).toHaveBeenCalled();
  });
});

describe("CockpitScreen con original", () => {
  it("muestra el enlace al original y la vista previa de la primera página de un PDF", () => {
    render(<CockpitScreen detalle={detalleCaso1({ formato: "pdf", num_paginas: 2, nombre_archivo: "informe.pdf" })} onContinuar={() => {}} />);
    expect(screen.getByRole("link", { name: /ver original/i })).toHaveAttribute("href", "/api/documentos/DOC-CLIN-2026-8942/original");
    expect(screen.getByRole("img", { name: /página 1/i })).toHaveAttribute("src", "/api/documentos/DOC-CLIN-2026-8942/vista_previa?pagina=1");
  });
});
