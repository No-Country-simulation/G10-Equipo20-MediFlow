/**
 * Uso clínico: firma en el momento del acuse, estados que no se invierten,
 * aviso de sistema degradado y lenguaje clínico en lugar de códigos del sistema.
 */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { etiquetaConcepto } from "../app/mensajes";
import { AppRouter } from "../app/router";
import { detalleCaso1, resultadoCaso1 } from "../test/fixtures";

const hace = (min: number) => new Date(Date.now() - min * 60000).toISOString();

const ALERTAS = [
  { documento_id: "DOC-RECIENTE", version: 1, nivel: "Crítico", canal: "Slack", destinatario: "Jefe de Urgencias", mensaje: "Alerta Crítica. Doc: DOC-RECIENTE.", concepto: "IAM_STEMI",
    emitida_en: hace(3), plazo_minutos: 15, estado_acuse: "pendiente", acusado_por: null, acusado_en: null, estado_documento: "EN_REVISION_HUMANA" },
  { documento_id: "DOC-VIEJA", version: 1, nivel: "Crítico", canal: "Slack", destinatario: "Jefe de Urgencias", mensaje: "Alerta Crítica. Doc: DOC-VIEJA.", concepto: "TEP_AGUDO",
    emitida_en: hace(90), plazo_minutos: 15, estado_acuse: "pendiente", acusado_por: null, acusado_en: null, estado_documento: "EN_REVISION_HUMANA" },
  { documento_id: "DOC-CERRADA", version: 1, nivel: "Crítico", canal: "Slack", destinatario: "Jefe de Urgencias", mensaje: "Alerta Crítica. Doc: DOC-CERRADA.", concepto: "EDEMA_AGUDO_PULMON",
    emitida_en: hace(200), plazo_minutos: 15, estado_acuse: "acusado", acusado_por: "jefe.rojas", acusado_en: hace(190), estado_documento: "ENRUTADO" },
];

function itemCola(id: string, motivo: string, nivel = "Rutina") {
  return { documento_id: id, version: 1, nivel_prioridad: nivel, motivo_auditoria: motivo, campos_dudosos: [], tipo: "No Clasificable", creado_en: hace(30), plazo_minutos: 1440 };
}

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.spyOn(api, "listarAlertas").mockResolvedValue(ALERTAS as never);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "obtenerResumen").mockResolvedValue({ total: 3, por_estado: { EN_REVISION_HUMANA: 2, ENTREGADO: 1 }, por_prioridad: { "Crítico": 2, Rutina: 1 }, en_revision: 2, alertas_sin_acuse: 2, recetas_por_verificar: 0, ordenes_por_autorizar: 0, enrutados: 0, entregados_hoy: 1 });
});
afterEach(() => vi.restoreAllMocks());

describe("acuse con firma en el momento (RN-Q5)", () => {
  it("Dar acuse siempre responde: pregunta quién da el acuse y confirma con ese nombre", async () => {
    const acusar = vi.spyOn(api, "acusarAlerta").mockResolvedValue({ estado_acuse: "acusado", acusado_por: "ana.torres", estado: "EN_REVISION_HUMANA" });
    render(<AppRouter rutaInicial="/alertas" rolInicial="auditor_clinico" />);
    const filas = await screen.findAllByTestId("fila-alerta");
    const boton = within(filas[0]).getByRole("button", { name: /dar acuse/i });
    expect(boton).toBeEnabled();
    await userEvent.click(boton);
    const quien = within(filas[0]).getByLabelText(/quién da el acuse/i);
    expect(quien).toHaveValue("");
    expect(within(filas[0]).getByRole("button", { name: /confirmar acuse/i })).toBeDisabled();
    await userEvent.type(quien, "ana.torres");
    await userEvent.click(within(filas[0]).getByRole("button", { name: /confirmar acuse/i }));
    await waitFor(() => expect(acusar).toHaveBeenCalledWith("DOC-VIEJA", "ana.torres"));
  });

  it("fuera de la pantalla compartida la firma de la barra lateral se propone, y se puede cancelar", async () => {
    const acusar = vi.spyOn(api, "acusarAlerta");
    render(<AppRouter rutaInicial="/alertas" rolInicial="auditor_clinico" />);
    await userEvent.type(await screen.findByLabelText(/firmo como/i), "ana.torres");
    const fila = (await screen.findAllByTestId("fila-alerta"))[0];
    await userEvent.click(within(fila).getByRole("button", { name: /dar acuse/i }));
    expect(within(fila).getByLabelText(/quién da el acuse/i)).toHaveValue("ana.torres");
    await userEvent.click(within(fila).getByRole("button", { name: /cancelar/i }));
    expect(within(fila).queryByLabelText(/quién da el acuse/i)).not.toBeInTheDocument();
    expect(acusar).not.toHaveBeenCalled();
  });

  it("en la pantalla compartida de urgencias la firma no se guarda ni se propone", async () => {
    const { unmount } = render(<AppRouter rutaInicial="/alertas" rolInicial="jefe_urgencias" />);
    await userEvent.type(await screen.findByLabelText(/firmo como/i), "dr.perez");
    const fila = (await screen.findAllByTestId("fila-alerta"))[0];
    await userEvent.click(within(fila).getByRole("button", { name: /dar acuse/i }));
    expect(within(fila).getByLabelText(/quién da el acuse/i)).toHaveValue("");
    unmount();
    expect(localStorage.getItem("mediflow.usuario")).toBeNull();
    render(<AppRouter rutaInicial="/alertas" rolInicial="jefe_urgencias" />);
    expect(await screen.findByLabelText(/firmo como/i)).toHaveValue("");
  });

  it("en el detalle, el acuse también pregunta quién lo da", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(detalleCaso1({ estado: "EN_REVISION_HUMANA" }));
    const acusar = vi.spyOn(api, "acusarAlerta").mockResolvedValue({ estado_acuse: "acusado", acusado_por: "jefe.rojas", estado: "EN_REVISION_HUMANA" });
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="jefe_urgencias" />);
    const alerta = await screen.findByTestId("alerta-documento");
    await userEvent.click(within(alerta).getByRole("button", { name: /dar acuse/i }));
    await userEvent.type(within(alerta).getByLabelText(/quién da el acuse/i), "jefe.rojas");
    await userEvent.click(within(alerta).getByRole("button", { name: /confirmar acuse/i }));
    await waitFor(() => expect(acusar).toHaveBeenCalledWith("DOC-CLIN-2026-8942", "jefe.rojas"));
  });
});

describe("estados que no se invierten y menos alarma de fondo", () => {
  it("las alertas van de la más vencida a la más reciente y las acusadas al final", async () => {
    render(<AppRouter rutaInicial="/alertas" rolInicial="jefe_urgencias" />);
    const filas = await screen.findAllByTestId("fila-alerta");
    expect(filas.map((f) => within(f).getByRole("link", { name: /DOC-/ }).textContent)).toEqual(["DOC-VIEJA", "DOC-RECIENTE", "DOC-CERRADA"]);
  });

  it("una alerta escalada se marca al menos tan fuerte como un crítico", async () => {
    render(<AppRouter rutaInicial="/alertas" rolInicial="jefe_urgencias" />);
    const vieja = (await screen.findAllByTestId("fila-alerta"))[0];
    expect(within(vieja).getByText(/escalada/i).closest(".tag")).toHaveClass("critico");
    expect(screen.getByText(/1 alerta escalada/i)).toBeInTheDocument();
    expect(document.querySelector(".banner-alertas")).toBeNull();  // la página ya es la lista: el banner no se repite
  });

  it("cuando muchos casos comparten el fallo técnico se explica una vez, pero ningún crítico queda plegado", async () => {
    vi.spyOn(api, "colaRevision").mockResolvedValue([
      itemCola("DOC-DUDA", "campo_dudoso", "Urgente"),
      itemCola("FT-1", "fallo_tecnico", "Crítico"), itemCola("FT-2", "fallo_tecnico"), itemCola("FT-3", "fallo_tecnico"), itemCola("FT-4", "fallo_tecnico"),
    ] as never);
    render(<AppRouter rutaInicial="/revision" rolInicial="auditor_clinico" />);
    const aviso = await screen.findByTestId("sistema-degradado");
    expect(aviso).toHaveTextContent(/motor de extracción/i);
    expect(aviso).toHaveTextContent(/4 documentos/);
    expect(aviso).toHaveTextContent(/desde las \d{1,2}:\d{2}/);
    expect(aviso).toHaveClass("urgente");  // una caída no se pinta con el verde de la calma
    // el crítico por fallo técnico sale a la tabla principal; lo plegado es solo lo no crítico
    const visibles = screen.getAllByTestId("fila-cola").filter((f) => !f.closest("details"));
    expect(visibles.map((f) => within(f).getByRole("link", { name: /revisar/i }).textContent)).toEqual(["DOC-DUDA", "FT-1"]);
    const grupo = screen.getByTestId("grupo-fallo-tecnico");
    expect(grupo).toHaveTextContent(/3 documentos/);
    expect(grupo).not.toHaveAttribute("open");
  });

  it("si todo es fallo técnico y no hay críticos, el grupo se muestra abierto", async () => {
    vi.spyOn(api, "colaRevision").mockResolvedValue([itemCola("FT-1", "fallo_tecnico"), itemCola("FT-2", "fallo_tecnico"), itemCola("FT-3", "fallo_tecnico")] as never);
    render(<AppRouter rutaInicial="/revision" rolInicial="auditor_clinico" />);
    expect(await screen.findByTestId("grupo-fallo-tecnico")).toHaveAttribute("open");
  });

  it("Métricas avisa que el motor está caído y que los indicadores no son representativos", async () => {
    vi.spyOn(api, "obtenerMetricas").mockResolvedValue({
      periodo_dias: 30, calculado_en: new Date().toISOString(), documentos: 51, procesados: 51, por_estado: { EN_REVISION_HUMANA: 51 }, por_prioridad: { "Crítico": 16, Rutina: 35 },
      tasa_automatizacion: 0, revision_por_motivo: { fallo_tecnico: { n: 51, porcentaje: 1 } }, tiempo_por_etapa_s: {},
      acuse_criticos: { emitidas: 16, acusadas: 0, pendientes: 16, minutos_promedio: null, dentro_de_plazo: 0, plazo_min: 15 },
      limite_correccion_campo: 0.1, correccion_por_campo: [], avisos: [], falsos_negativos_criticos: { n: 0, documentos: [], criticos_totales: 16, tasa: 0 },
      versiones: {}, tokens: { entrada: 0, salida: 0 },
    } as never);
    render(<AppRouter rutaInicial="/metricas" rolInicial="gestor" />);
    const aviso = await screen.findByTestId("sistema-degradado");
    expect(aviso).toHaveTextContent(/100 %/);
    expect(aviso).toHaveTextContent(/no son representativos/i);
  });
});

describe("alertas en vivo (pantalla de urgencias)", () => {
  afterEach(() => vi.useRealTimers());

  it("la lista se refresca sola, dice cuándo se actualizó y marca las alertas nuevas", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const listar = vi.spyOn(api, "listarAlertas").mockResolvedValueOnce(ALERTAS as never).mockResolvedValue([
      { ...ALERTAS[0], documento_id: "DOC-NUEVA", concepto: "DISECCION_AORTICA", emitida_en: hace(1) }, ...ALERTAS,
    ] as never);
    render(<AppRouter rutaInicial="/alertas" rolInicial="jefe_urgencias" />);
    await screen.findAllByTestId("fila-alerta");
    expect(screen.getByTestId("actualizado")).toHaveTextContent(/actualizado/i);
    expect(screen.queryByText("DOC-NUEVA")).not.toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    const nueva = (await screen.findByText("DOC-NUEVA")).closest("tr")!;
    expect(nueva).toHaveTextContent(/nueva/i);
    expect(nueva).toHaveTextContent("Disección aórtica");
    expect(listar.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(document.title).toMatch(/^\(3\)/);
  });

  it("si una actualización falla, conserva la lista y avisa que puede estar desactualizada", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(api, "listarAlertas").mockResolvedValueOnce(ALERTAS as never).mockRejectedValue(new Error("sin red"));
    render(<AppRouter rutaInicial="/alertas" rolInicial="jefe_urgencias" />);
    await screen.findAllByTestId("fila-alerta");
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(await screen.findByRole("alert")).toHaveTextContent(/desactualizada/i);
    expect(screen.getAllByTestId("fila-alerta")).toHaveLength(3);
  });
});

describe("lenguaje clínico", () => {
  it("traduce los conceptos críticos del pack a español", () => {
    expect(etiquetaConcepto("TEP_AGUDO")).toBe("Tromboembolismo pulmonar agudo");
    expect(etiquetaConcepto("IAM_STEMI")).toBe("Infarto con elevación del ST");
    expect(etiquetaConcepto("EDEMA_AGUDO_PULMON")).toBe("Edema agudo de pulmón");
    expect(etiquetaConcepto("CONCEPTO_NUEVO_AMPLIADO")).toBe("Concepto nuevo ampliado");
  });

  it("la línea de tiempo y los hallazgos hablan en español; las trazas técnicas quedan plegadas", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(detalleCaso1({
      transiciones: [
        { de_estado: null, a_estado: "RECIBIDO", actor: "sistema", motivo: "documento recibido", fecha_hora: "2026-09-25T10:00:00Z" },
        { de_estado: "VALIDADO", a_estado: "FALLO_TECNICO", actor: "sistema", motivo: "fallo_tecnico: FalloLLM: reintentos agotados (3): OPENAI_API_KEY no configurada", fecha_hora: "2026-09-25T10:00:02Z" },
        { de_estado: "FALLO_TECNICO", a_estado: "EN_REVISION_HUMANA", actor: "sistema", motivo: "fallo_tecnico", fecha_hora: "2026-09-25T10:00:03Z" },
      ],
    }));
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /^decisión/i });
    const eventos = screen.getAllByTestId("evento");
    expect(eventos.map((e) => e.querySelector(".estado")?.textContent)).toEqual(expect.arrayContaining([expect.stringMatching(/^Revisión humana/), expect.stringMatching(/^Fallo técnico/)]));
    const fallo = eventos.find((e) => /Fallo técnico/.test(e.textContent ?? ""))!;
    expect(within(fallo).getByText(/el motor de extracción no respondió/i)).toBeVisible();
    expect(fallo.querySelector("details")).not.toHaveAttribute("open");
    expect(screen.getAllByText("Tromboembolismo pulmonar agudo").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("TEP_AGUDO")).not.toBeInTheDocument();
    expect(screen.getByText(/detalle técnico: reglas disparadas/i).closest("details")).not.toHaveAttribute("open");
  });

  it("corregir se hace eligiendo el campo por su nombre, con ruta técnica solo como último recurso", async () => {
    const resultado = resultadoCaso1({ estado: "EN_REVISION_HUMANA", evaluacion: { requiere_auditoria_humana: true, motivo_auditoria: "campo_dudoso", campos_dudosos: ["profesional"] } });
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(detalleCaso1({ estado: "EN_REVISION_HUMANA", resultado }));
    const resolver = vi.spyOn(api, "resolverRevision").mockResolvedValue({ documento_id: "DOC-CLIN-2026-8942", estado: "ENRUTADO", resultado: resultadoCaso1() });
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="auditor_clinico" />);
    await screen.findByRole("heading", { name: /^decisión/i });
    await userEvent.type(screen.getByLabelText(/firmo como/i), "ana");
    await userEvent.click(screen.getByRole("button", { name: /^corregir/i }));
    const campo = screen.getByLabelText(/campo a corregir/i);
    expect(within(campo).getByRole("option", { name: /registro del profesional/i })).toBeInTheDocument();
    await userEvent.selectOptions(campo, "extraccion.profesional.registro_profesional");
    await userEvent.type(screen.getByLabelText(/valor corregido/i), "RM 45678");
    await userEvent.click(screen.getByRole("button", { name: /aplicar corrección/i }));
    await waitFor(() => expect(resolver).toHaveBeenCalledWith("DOC-CLIN-2026-8942", expect.objectContaining({
      accion: "corregir", correcciones: { "extraccion.profesional.registro_profesional": "RM 45678" },
    })));
    expect(screen.queryByLabelText(/ruta técnica/i)).not.toBeInTheDocument();
  });

  it("el inicio muestra los estados con su nombre, no el código", async () => {
    render(<AppRouter rutaInicial="/inicio" rolInicial="auditor_clinico" />);
    expect(await screen.findByText("Revisión humana")).toBeInTheDocument();
    expect(screen.queryByText(/en revision humana/i)).not.toBeInTheDocument();
  });
});
