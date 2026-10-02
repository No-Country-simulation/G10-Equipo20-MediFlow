import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { detalleCaso1 } from "../test/fixtures";
import { calcularPlazo, plazoDeRevision } from "./plazos";
import { rolDesdeApi, rolPorId, rolPuedeVer, ROLES } from "./roles";
import { AppRouter } from "./router";

const LISTADO = {
  items: [
    { documento_id: "DOC-CLIN-2026-8942", version: 1, estado: "EN_REVISION_HUMANA", nivel_prioridad: "Crítico", tipo_contenido: "pdf", formato: "pdf",
      nombre_archivo: "cardio_mixed.pdf", canal_origen: "Guardia_Emergencias", creado_en: new Date(Date.now() - 4 * 60000).toISOString(),
      tipo: "Informe de Imágenes", motivo_auditoria: "critico_baja_confianza", codigo_error: null, num_paginas: 2 },
    { documento_id: "DOC-REC-2026-0302", version: 1, estado: "ENTREGADO", nivel_prioridad: "Rutina", tipo_contenido: "texto", formato: "txt",
      nombre_archivo: null, canal_origen: "Consulta_Ambulatoria", creado_en: new Date(Date.now() - 60 * 60000).toISOString(),
      tipo: "Receta Médica", motivo_auditoria: null, codigo_error: null, num_paginas: 1 },
  ],
  total: 2, limit: 20, offset: 0,
};

const ALERTAS = [
  { documento_id: "DOC-CLIN-2026-8942", version: 1, nivel: "Crítico", canal: "Slack", destinatario: "Jefe de Urgencias",
    mensaje: "Alerta Crítica. Doc: DOC-CLIN-2026-8942. Nivel: Crítico. Requiere acuse.", concepto: "TEP_AGUDO",
    emitida_en: new Date(Date.now() - 3 * 60000).toISOString(), plazo_minutos: 15, estado_acuse: "pendiente", acusado_por: null, acusado_en: null, estado_documento: "EN_REVISION_HUMANA" },
];

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarDocumentos").mockResolvedValue(LISTADO as never);
  vi.spyOn(api, "listarAlertas").mockResolvedValue(ALERTAS as never);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
});
afterEach(() => vi.restoreAllMocks());

describe("roles (RN-K1, RN-K2)", () => {
  it("cada rol tiene navegación propia y los no clínicos no ven documentos", () => {
    expect(ROLES.map((r) => r.id)).toEqual(["auditor_clinico", "quimico_farmaceutico", "auditor_autorizaciones", "jefe_urgencias", "gestor", "administrador"]);
    expect(rolPuedeVer(rolPorId("gestor"), "/documentos")).toBe(false);
    expect(rolPuedeVer(rolPorId("gestor"), "/documentos/DOC-1")).toBe(false);
    expect(rolPuedeVer(rolPorId("auditor_clinico"), "/documentos/DOC-1")).toBe(true);
    expect(rolPuedeVer(rolPorId("quimico_farmaceutico"), "/revision")).toBe(false);
    expect(rolPorId("jefe_urgencias").modoDiscreto).toBe(true);
  });
});

describe("roles como datos del backend (tabla K, RN-K1)", () => {
  it("el menú se arma con las secciones que entrega la API, no con las escritas en la interfaz", async () => {
    vi.spyOn(api, "listarRoles").mockResolvedValue([
      { id: "quimico_farmaceutico", nombre: "Químico farmacéutico", descripcion: "x", secciones: ["inicio", "farmacia", "documentos", "alertas"], acciones: ["verificar_receta"],
        ve_documentos: true, ruta_inicial: "/farmacia", modo_discreto: false, alto_contraste: false, pantalla_compartida: false },
    ]);
    render(<AppRouter rutaInicial="/farmacia" rolInicial="quimico_farmaceutico" />);
    const nav = screen.getByRole("navigation", { name: /principal/i });
    expect(await within(nav).findByRole("link", { name: /alertas críticas/i })).toBeInTheDocument();  // sección agregada por el backend
    expect(within(nav).queryByRole("link", { name: /cola de revisión/i })).toBeNull();
  });

  it("una sección que la interfaz no conoce no rompe el menú", () => {
    const rol = rolDesdeApi({ id: "gestor", nombre: "Gestor", descripcion: "x", secciones: ["inicio", "tablero_nuevo", "metricas"], acciones: [],
      ve_documentos: false, ruta_inicial: "/metricas", modo_discreto: true, alto_contraste: false, pantalla_compartida: false });
    expect(rol.navegacion.map((n) => n.ruta)).toEqual(["/inicio", "/metricas"]);
  });
});

describe("plazos (RN-J2, RN-F2)", () => {
  it("calcula restantes, apremio y vencimiento", () => {
    const ahora = new Date("2026-09-26T10:15:00Z");
    expect(calcularPlazo("2026-09-26T10:03:00Z", 15, ahora)).toMatchObject({ vencido: false, apremia: true, texto: "3 min restantes" });
    expect(calcularPlazo("2026-09-26T09:00:00Z", 15, ahora)).toMatchObject({ vencido: true, texto: "vencido hace 1 h" });
    expect(plazoDeRevision("EN_REVISION_HUMANA", "Urgente", "2026-09-26T10:00:00Z", ahora)?.texto).toBe("1 h 45 min restantes");
    expect(plazoDeRevision("ENRUTADO", "Crítico", "2026-09-26T10:00:00Z", ahora)).toBeNull();
  });
});

describe("shell de la aplicación", () => {
  it("muestra el logo, la navegación del rol y el banner de alertas sin datos del paciente (RN-Q4)", async () => {
    render(<AppRouter rutaInicial="/documentos" />);
    expect(screen.getByRole("img", { name: /mediflow/i })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: /principal/i });
    expect(within(nav).getByRole("link", { name: /cola de revisión/i })).toBeInTheDocument();
    const banner = await screen.findByRole("status", { name: /alertas críticas/i });
    expect(banner).toHaveTextContent("1 alerta crítica sin acuse");
    expect(banner).toHaveTextContent("DOC-CLIN-2026-8942");
    expect(banner).not.toHaveTextContent("Mendes");
  });

  it("cambiar de rol cambia la navegación y lleva a su inicio", async () => {
    render(<AppRouter rutaInicial="/documentos" />);
    await userEvent.selectOptions(screen.getByLabelText(/rol/i), "quimico_farmaceutico");
    const nav = screen.getByRole("navigation", { name: /principal/i });
    expect(within(nav).getByRole("link", { name: /farmacia/i })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: /cola de revisión/i })).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /farmacia/i })).toBeInTheDocument();
  });

  it("un rol sin acceso a una ruta ve el aviso de acceso restringido (RN-K2)", async () => {
    render(<AppRouter rutaInicial="/documentos/DOC-1" rolInicial="gestor" />);
    expect(await screen.findByText(/sin acceso para este rol/i)).toBeInTheDocument();
    expect(api.listarDocumentos).not.toHaveBeenCalled();
  });
});

describe("página Documentos", () => {
  it("lista los documentos con prioridad, estado, plazo y enlace al detalle", async () => {
    render(<AppRouter rutaInicial="/documentos" />);
    const filas = await screen.findAllByTestId("fila-documento");
    expect(filas).toHaveLength(2);
    expect(filas[0]).toHaveTextContent("DOC-CLIN-2026-8942");
    expect(filas[0]).toHaveTextContent("Crítico");
    expect(filas[0]).toHaveTextContent("Revisión humana");
    expect(filas[0]).toHaveTextContent(/restantes/);
    expect(filas[1]).toHaveTextContent("Entregado");
    expect(within(filas[0]).getByRole("link", { name: /abrir/i })).toHaveAttribute("href", "/documentos/DOC-CLIN-2026-8942");
    expect(screen.queryByText(/Mendes/)).not.toBeInTheDocument();
  });

  it("los filtros consultan la API con sus parámetros", async () => {
    render(<AppRouter rutaInicial="/documentos" />);
    await screen.findAllByTestId("fila-documento");
    await userEvent.selectOptions(screen.getByLabelText(/^estado/i), "EN_REVISION_HUMANA");
    await waitFor(() => expect(api.listarDocumentos).toHaveBeenLastCalledWith(expect.objectContaining({ estado: "EN_REVISION_HUMANA" })));
    await userEvent.type(screen.getByLabelText(/buscar/i), "REC{enter}");
    await waitFor(() => expect(api.listarDocumentos).toHaveBeenLastCalledWith(expect.objectContaining({ q: "REC" })));
  });

  it("carga un archivo desde la zona de carga y refresca la tabla", async () => {
    const enviar = vi.spyOn(api, "enviarArchivo").mockResolvedValue(detalleCaso1());
    render(<AppRouter rutaInicial="/documentos" />);
    await screen.findAllByTestId("fila-documento");
    await userEvent.type(screen.getByLabelText(/^id del documento/i), "DOC-NUEVO");
    const archivo = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "informe.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByLabelText(/elegir archivo/i), archivo);
    await userEvent.click(screen.getByRole("button", { name: /cargar documento/i }));
    await waitFor(() => expect(enviar).toHaveBeenCalledWith(archivo, expect.objectContaining({ documento_id: "DOC-NUEVO" })));
    await waitFor(() => expect(api.listarDocumentos).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("status", { name: /resultado de la carga/i })).toHaveTextContent(/Crítico/);
  });

  it("permite pegar texto en lugar de un archivo", async () => {
    const enviarTexto = vi.spyOn(api, "enviarDocumento").mockResolvedValue(detalleCaso1());
    render(<AppRouter rutaInicial="/documentos" />);
    await screen.findAllByTestId("fila-documento");
    await userEvent.click(screen.getByRole("button", { name: /pegar texto/i }));
    await userEvent.type(screen.getByLabelText(/^id del documento/i), "DOC-TXT");
    await userEvent.type(screen.getByLabelText(/texto clínico/i), "TC de tórax: TEP agudo.");
    await userEvent.click(screen.getByRole("button", { name: /cargar documento/i }));
    await waitFor(() => expect(enviarTexto).toHaveBeenCalledWith(expect.objectContaining({ documento_id: "DOC-TXT", tipo_contenido: "texto" })));
  });

  it("traduce el código de rechazo a un mensaje legible", async () => {
    vi.spyOn(api, "enviarArchivo").mockResolvedValue({ ...detalleCaso1(), estado: "RECHAZADO", codigo_error: "extension_no_coincide", resultado: null });
    render(<AppRouter rutaInicial="/documentos" />);
    await screen.findAllByTestId("fila-documento");
    await userEvent.type(screen.getByLabelText(/^id del documento/i), "DOC-X");
    await userEvent.upload(screen.getByLabelText(/elegir archivo/i), new File([new Uint8Array([1])], "x.png", { type: "image/png" }));
    await userEvent.click(screen.getByRole("button", { name: /cargar documento/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/la extensión no coincide con el contenido/i);
  });
});

describe("menú compacto (pantallas angostas)", () => {
  it("el botón de menú despliega la navegación y navegar la cierra", async () => {
    render(<AppRouter rutaInicial="/inicio" rolInicial="auditor_clinico" />);
    const boton = await screen.findByRole("button", { name: /abrir menú/i });
    expect(boton).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(boton);
    expect(screen.getByRole("button", { name: /cerrar menú/i })).toHaveAttribute("aria-expanded", "true");
    expect(document.querySelector(".lateral")).toHaveClass("abierta");
    await userEvent.click(within(screen.getByRole("navigation", { name: /principal/i })).getByRole("link", { name: /documentos/i }));
    await waitFor(() => expect(document.querySelector(".lateral")).not.toHaveClass("abierta"));
    expect(screen.getByRole("button", { name: /abrir menú/i })).toBeInTheDocument();
  });
});

describe("alto contraste (pantallas compartidas de urgencias)", () => {
  afterEach(() => document.documentElement.removeAttribute("data-contraste"));

  it("el jefe de urgencias arranca en alto contraste y el auditor no", async () => {
    const { unmount } = render(<AppRouter rutaInicial="/inicio" rolInicial="jefe_urgencias" />);
    const interruptor = await screen.findByRole("switch", { name: /alto contraste/i });
    expect(interruptor).toBeChecked();
    expect(document.documentElement).toHaveAttribute("data-contraste", "alto");
    unmount();
    document.documentElement.removeAttribute("data-contraste");
    render(<AppRouter rutaInicial="/inicio" rolInicial="auditor_clinico" />);
    expect(await screen.findByRole("switch", { name: /alto contraste/i })).not.toBeChecked();
    expect(document.documentElement).not.toHaveAttribute("data-contraste");
  });

  it("se alterna desde la barra lateral y la elección se recuerda", async () => {
    const { unmount } = render(<AppRouter rutaInicial="/inicio" rolInicial="auditor_clinico" />);
    await userEvent.click(await screen.findByRole("switch", { name: /alto contraste/i }));
    expect(document.documentElement).toHaveAttribute("data-contraste", "alto");
    unmount();
    render(<AppRouter rutaInicial="/inicio" rolInicial="auditor_clinico" />);
    expect(await screen.findByRole("switch", { name: /alto contraste/i })).toBeChecked();
  });
});
