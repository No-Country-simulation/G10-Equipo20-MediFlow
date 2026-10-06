/**
 * Verificación del profesional (RN-A7): el documento dice si el firmante está en el padrón de la instalación,
 * con el enlace al registro nacional; el administrador mantiene el padrón y anota la consulta en ReTHUS.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";
import { detalleCaso1, resultadoCaso1 } from "../test/fixtures";
import type { ProfesionalRegistrado } from "../types";

const RETHUS = "https://web.sispro.gov.co/THS/Cliente/ConsultasPublicas/ConsultaPublicaDeTHxIdentificacion.aspx";
const AHORA = new Date().toISOString();
const ROJAS: ProfesionalRegistrado = { id: 1, registro: "45678", nombre: "Andrés Rojas", profesion: "Medicina", tipo_documento: "CC", numero_documento: "80123456", activo: true, creado_por: "admin.root", creado_en: AHORA, registro_consultado_en: null, registro_consultado_por: null };
const PACK = { pais: "CO", nombre: "Colombia", version_pack: "8", formato: { separador_decimal: ",", separador_miles: ".", formato_fecha: "DD/MM/AAAA" },
  terminologia: { diagnosticos: "dual", procedimientos: "CUPS", medicamentos: "DCI" },
  identidad_profesional: { registro: "ReTHUS", ambito: "nacional", verificacion_en_linea: { disponible: true, automatica: false, url: RETHUS } },
  tipos_documento_paciente: {}, coberturas: {}, urgencias: {}, retencion: { anios: 15 }, datos_personales: { norma: "Ley 1581 de 2012" },
  listas: { hallazgos_criticos: 10, alto_riesgo: 5, control_especial: 3 }, por_confirmar: [] };

function conVerificacion(estado: "verificado" | "no_encontrado" | "sin_datos" | "no_aplica", detalle: string) {
  const r = resultadoCaso1();
  return detalleCaso1({ alerta: null, resultado: { ...r, extraccion: { ...r.extraccion, profesional: { ...r.extraccion.profesional, verificacion: { estado, fuente: "padrón de profesionales de la instalación", detalle, enlace_consulta: RETHUS, consultado_en_registro_en: null } } } } });
}

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "listarDocumentos").mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.spyOn(api, "listarUsuarios").mockResolvedValue([]);
  vi.spyOn(api, "listarAccesos").mockResolvedValue([]);
  vi.spyOn(api, "puestaEnMarcha").mockResolvedValue({ activable: false, requisitos: [] } as never);
  vi.spyOn(api, "obtenerPack").mockResolvedValue(PACK as never);
  vi.spyOn(api, "listarProfesionales").mockResolvedValue([ROJAS]);
});
afterEach(() => vi.restoreAllMocks());

describe("el documento muestra la verificación del profesional (RN-A7)", () => {
  it("verificado en el padrón, con el enlace a ReTHUS", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(conVerificacion("verificado", "registro 45678 de Andrés Rojas"));
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="auditor_clinico" />);
    const verificacion = await screen.findByTestId("verificacion-profesional");
    expect(verificacion).toHaveTextContent("Verificado en el padrón");
    expect(within(verificacion).getByRole("link", { name: /consultar en rethus/i })).toHaveAttribute("href", RETHUS);
  });

  it("no encontrado se muestra como aviso, sin bloquear nada", async () => {
    vi.spyOn(api, "consultarDocumento").mockResolvedValue(conVerificacion("no_encontrado", "registro 45678 no está en el padrón"));
    render(<AppRouter rutaInicial="/documentos/DOC-CLIN-2026-8942" rolInicial="auditor_clinico" />);
    const verificacion = await screen.findByTestId("verificacion-profesional");
    expect(verificacion).toHaveTextContent("No está en el padrón");
    expect(screen.getByRole("heading", { name: /^decisión/i })).toBeInTheDocument();
  });
});

describe("el administrador mantiene el padrón", () => {
  it("lista el padrón, agrega un profesional y anota la consulta en el registro nacional", async () => {
    const crear = vi.spyOn(api, "crearProfesional").mockResolvedValue({ ...ROJAS, id: 2, registro: "78901", nombre: "Carolina Duque", numero_documento: null, tipo_documento: null });
    const anotar = vi.spyOn(api, "anotarConsultaRegistro").mockResolvedValue({ ...ROJAS, registro_consultado_en: AHORA, registro_consultado_por: "admin.root" });
    render(<AppRouter rutaInicial="/administracion" rolInicial="administrador" />);
    const padron = await screen.findByTestId("padron-profesionales");
    const fila = await within(padron).findByTestId("fila-profesional");
    expect(fila).toHaveTextContent("45678");
    expect(fila).toHaveTextContent("Sin consultar");
    expect(within(padron).getByRole("link", { name: /consultar rethus/i })).toHaveAttribute("href", RETHUS);

    await userEvent.type(within(padron).getByLabelText(/registro profesional/i), "RM 78901");
    await userEvent.type(within(padron).getByLabelText(/nombre del profesional/i), "Carolina Duque");
    await userEvent.click(within(padron).getByRole("button", { name: /agregar al padrón/i }));
    await waitFor(() => expect(crear).toHaveBeenCalledWith(expect.objectContaining({ registro: "RM 78901", nombre: "Carolina Duque" })));
    expect(await screen.findByText(/queda en el padrón con el registro 78901/i)).toBeInTheDocument();

    await userEvent.click(within(fila).getByRole("button", { name: /anotar la consulta en el registro nacional de andrés rojas/i }));
    await waitFor(() => expect(anotar).toHaveBeenCalledWith(1));
    expect(fila).toHaveTextContent("Consultado");
    expect(fila).toHaveTextContent("admin.root");
  }, 15_000);
});
