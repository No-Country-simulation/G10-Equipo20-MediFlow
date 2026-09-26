import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import { AppRouter } from "../app/router";

const RANGO = (base: number, min: number, max: number, extra = {}) => ({ min, max, solo_a_la_baja: false, base, efectivo: base, ...extra });

const CONFIGURACION = {
  vigente: { id: null, numero: 0, autor: "sistema", motivo: "valores iniciales de la sección 7", cambios: { umbrales: {}, ampliaciones: {} }, vigente_desde: null, estado: "vigente" },
  umbrales_base: { confianza: { clasificacion: 0.85, identidad_paciente: 0.95, medicamento_dosis: 0.95, diagnostico_codigo: 0.9, profesional: 0.85, resto: 0.8, texto_ilegible_max: null }, consistencia: { tolerancia_edad_anios: 1 }, tiempos: { comunicacion_critico_min: 60, escalamiento_sin_acuse_min: 15, atencion_urgente_h: 24, cola_revision: { critico_min: 15, urgente_h: 2, rutina_h_habiles: 24 } } },
  umbrales_efectivos: { confianza: { clasificacion: 0.85, identidad_paciente: 0.95, medicamento_dosis: 0.95, diagnostico_codigo: 0.9, profesional: 0.85, resto: 0.8, texto_ilegible_max: null }, consistencia: { tolerancia_edad_anios: 1 }, tiempos: { comunicacion_critico_min: 60, escalamiento_sin_acuse_min: 15, atencion_urgente_h: 24, cola_revision: { critico_min: 15, urgente_h: 2, rutina_h_habiles: 24 } } },
  rangos: {
    "confianza.clasificacion": RANGO(0.85, 0.7, 0.99), "confianza.identidad_paciente": RANGO(0.95, 0.9, 0.99), "confianza.medicamento_dosis": RANGO(0.95, 0.9, 0.99),
    "confianza.diagnostico_codigo": RANGO(0.9, 0.8, 0.99), "confianza.profesional": RANGO(0.85, 0.75, 0.99), "confianza.resto": RANGO(0.8, 0.7, 0.99),
    "consistencia.tolerancia_edad_anios": RANGO(1, 0, 3), "tiempos.comunicacion_critico_min": RANGO(60, 15, 60, { solo_a_la_baja: true }),
    "tiempos.escalamiento_sin_acuse_min": RANGO(15, 5, 30), "tiempos.atencion_urgente_h": RANGO(24, 4, 48),
    "tiempos.cola_revision.critico_min": RANGO(15, 5, 30), "tiempos.cola_revision.urgente_h": RANGO(2, 1, 8), "tiempos.cola_revision.rutina_h_habiles": RANGO(24, 8, 72),
  },
  no_configurable: { news2: { fr_bajo: 8, fr_alto: 25, spo2_bajo: 91, spo2_escala2_min: 88, spo2_escala2_max: 92, fc_bajo: 40, fc_alto: 131, pas_bajo: 90, total_critico: 7, edad_minima: 16 } },
  listas: { alto_riesgo: { base: ["warfarina", "apixaban"], ampliadas: [] }, control_especial: { base: ["morfina"], ampliadas: [] }, hallazgos_criticos: { base: ["TEP_AGUDO", "IAM_STEMI"], ampliados: [] } },
  calidad: { limite_correccion_campo: 0.1, simulacion_ultimos: 50 },
  propuestas: [
    { id: 7, numero: null, autor: "gestor.luis", motivo: "menos revisión", cambios: { umbrales: { "confianza.medicamento_dosis": 0.9 }, ampliaciones: { alto_riesgo: [], control_especial: [], hallazgos_criticos: [] } },
      simulacion: { documentos_evaluados: 10, sin_propuesta: 2, cambian: 3, mas_a_revision: 0, mas_automaticos: 3, detalle: [] }, toca_seguridad: true,
      aprobaciones: [{ usuario: "gestor.luis", fecha_hora: new Date().toISOString() }], aprobaciones_requeridas: 2, estado: "propuesta", creado_en: new Date().toISOString(), vigente_desde: null, vigente_hasta: null },
  ],
  historial: [
    { id: 3, numero: 1, autor: "gestor.ana", motivo: "cero errores de dosis", cambios: { umbrales: { "confianza.profesional": 0.9 }, ampliaciones: { alto_riesgo: [], control_especial: [], hallazgos_criticos: [] } },
      simulacion: null, toca_seguridad: false, aprobaciones: [{ usuario: "gestor.ana", fecha_hora: new Date().toISOString() }], aprobaciones_requeridas: 1, estado: "reemplazada", creado_en: new Date().toISOString(), vigente_desde: new Date().toISOString(), vigente_hasta: new Date().toISOString() },
  ],
};

const SIMULACION = {
  documentos_evaluados: 10, sin_propuesta: 2, cambian: 1, mas_a_revision: 1, mas_automaticos: 0,
  detalle: [{ documento_id: "REC-1", version: 1, tipo: "Receta Médica", estado_actual: "ENRUTADO", estado_simulado: "EN_REVISION_HUMANA", prioridad_actual: "Rutina", prioridad_simulada: "Rutina",
    motivo_actual: null, motivo_simulado: "campo_dudoso", destino_actual: "Farmacia_Hospitalaria", destino_simulado: "Cola_Revision_Humana", cambia: true }],
};

const METRICAS = {
  periodo_dias: 30, calculado_en: new Date().toISOString(), documentos: 3, procesados: 3, por_estado: { ENRUTADO: 1, ENTREGADO: 2 }, por_prioridad: { Rutina: 2, "Crítico": 1 },
  tasa_automatizacion: 0.667,
  revision_por_motivo: { campo_dudoso: { n: 1, porcentaje: 0.333 } },
  tiempo_por_etapa_s: { "RECIBIDO→VALIDADO": 0.012, "EN_REVISION_HUMANA→RESUELTO": 95.5 },
  acuse_criticos: { emitidas: 1, acusadas: 1, pendientes: 0, minutos_promedio: 3.2, dentro_de_plazo: 1, plazo_min: 15 },
  limite_correccion_campo: 0.1,
  correccion_por_campo: [{ campo: "extraccion.medicamentos.*.dosis", correcciones: 1, documentos_revisados: 1, tasa: 1, umbral_relacionado: "confianza.medicamento_dosis", supera_limite: true }],
  avisos: [{ regla: "RN-R4", campo: "extraccion.medicamentos.*.dosis", tasa: 1, limite: 0.1, umbral: "confianza.medicamento_dosis", umbral_actual: 0.95, umbral_propuesto: 0.97, propuesta: "subir confianza.medicamento_dosis de 0.95 a 0.97: la tasa de corrección 100% supera el límite 10%" }],
  falsos_negativos_criticos: { n: 0, documentos: [], criticos_totales: 1, tasa: 0 },
  versiones: { modelo_llm: { "gpt-4.1-mini": 3 }, version_prompt: { triaje_v1: 3 }, version_reglas: { "8": 3 }, pack: { CO: 3 } },
  tokens: { entrada: 3000, salida: 900 },
};

const USUARIOS = [
  { usuario: "aud.ana", nombre: "Ana Torres", rol: "auditor_clinico", tipo: "persona", activo: true, creado_por: "admin.root", creado_en: new Date().toISOString(), desactivado_en: null },
  { usuario: "bot.hce", nombre: "Integración HCE", rol: "gestor", tipo: "servicio", activo: false, creado_por: "admin.root", creado_en: new Date().toISOString(), desactivado_en: new Date().toISOString() },
];

const PUESTA = {
  listo: false,
  requisitos: [
    { clave: "pais", requisito: "País de la instalación con pack activo", cumplido: true, detalle: "CO · pack 1.0" },
    { clave: "base_legal", requisito: "Base legal de tratamiento declarada (RN-M8)", cumplido: false, detalle: "pendiente" },
    { clave: "auditor_clinico", requisito: "Al menos un auditor clínico activo", cumplido: true, detalle: "1 activos" },
    { clave: "jefe_urgencias", requisito: "Al menos un jefe de urgencias activo", cumplido: false, detalle: "0 activos" },
  ],
};

const PACK = { pais: "CO", nombre: "Colombia", version_pack: "1.0", formato: { separador_decimal: ",", separador_miles: ".", formato_fecha: "DD/MM/AAAA" },
  terminologia: { diagnosticos: "dual", fecha_cierre_transicion: null, procedimientos: "CUPS", procedimientos_estado: "verificado_en_parte", medicamentos: "DCI", codigo_medicamento: null },
  identidad_profesional: { registro: "RETHUS", ambito: "nacional", verificacion_en_linea: { disponible: true, automatica: false, url: null } },
  tipos_documento_paciente: { CC: { nombre: "Cédula de ciudadanía", estado: "verificado", nacional: true, no_identificado: false } },
  coberturas: { contributivo: { modelo: "EPS", entidad: "EPS", estado: "verificado" } }, urgencias: { autorizacion_previa: false, canales_sin_autorizacion: ["Guardia_Emergencias"], motivo_aviso_auditoria: "informe", triage_eleva_prioridad: false },
  retencion: { anios: 15, archivo_gestion_anios: 5, archivo_central_anios: 10, norma: "Res. 1995/1999", purga_automatica: false },
  datos_personales: { norma: "Ley 1581", datos_salud_sensibles: true, llm_es_transmision_internacional: true, solo_documentos_sinteticos_en_mvp: true },
  listas: { hallazgos_criticos: 12, alto_riesgo: 20, control_especial: 6 }, por_confirmar: ["terminologia.procedimientos"] };

const ACCESOS = [{ documento_id: "REC-1", usuario: "aud.ana", accion: "detalle", fecha_hora: new Date().toISOString() }];

beforeEach(() => {
  try { localStorage.clear(); } catch { /* sin storage */ }
  vi.spyOn(api, "listarAlertas").mockResolvedValue([]);
  vi.spyOn(api, "colaRevision").mockResolvedValue([]);
  vi.spyOn(api, "obtenerResumen").mockResolvedValue({ total: 3, por_estado: {}, por_prioridad: {}, en_revision: 0, alertas_sin_acuse: 0, recetas_por_verificar: 0, ordenes_por_autorizar: 0, enrutados: 0, entregados_hoy: 0 });
  vi.spyOn(api, "obtenerConfiguracion").mockResolvedValue(CONFIGURACION as never);
  vi.spyOn(api, "obtenerMetricas").mockResolvedValue(METRICAS as never);
  vi.spyOn(api, "listarUsuarios").mockResolvedValue(USUARIOS as never);
  vi.spyOn(api, "puestaEnMarcha").mockResolvedValue(PUESTA as never);
  vi.spyOn(api, "obtenerPack").mockResolvedValue(PACK as never);
  vi.spyOn(api, "listarAccesos").mockResolvedValue(ACCESOS as never);
});
afterEach(() => vi.restoreAllMocks());

describe("Configuración (RN-L1 a RN-L6)", () => {
  it("muestra los umbrales con su rango, lo no configurable en solo lectura y las listas base", async () => {
    render(<AppRouter rutaInicial="/configuracion" rolInicial="gestor" />);
    const dosis = await screen.findByLabelText(/medicamento y dosis/i);
    expect(dosis).toHaveValue(0.95);
    expect(dosis).toHaveAttribute("min", "0.9");
    expect(dosis).toHaveAttribute("max", "0.99");
    expect(screen.getByLabelText(/comunicación de un caso crítico/i)).toHaveAttribute("max", "60");
    const news2 = screen.getByTestId("no-configurable");
    expect(news2).toHaveTextContent(/no configurable/i);
    expect(within(news2).queryByRole("spinbutton")).toBeNull();
    expect(screen.getByTestId("lista-alto_riesgo")).toHaveTextContent("apixaban");
  });

  it("simula antes de proponer y la propuesta lleva solo lo que cambió", async () => {
    const simular = vi.spyOn(api, "simularConfiguracion").mockResolvedValue(SIMULACION as never);
    const proponer = vi.spyOn(api, "proponerConfiguracion").mockResolvedValue({ ...CONFIGURACION.propuestas[0], id: 8, toca_seguridad: false, aprobaciones: [], aprobaciones_requeridas: 1 } as never);
    render(<AppRouter rutaInicial="/configuracion" rolInicial="gestor" />);
    const dosis = await screen.findByLabelText(/medicamento y dosis/i);
    await userEvent.clear(dosis);
    await userEvent.type(dosis, "0.98");
    await userEvent.click(screen.getByRole("button", { name: /simular/i }));
    await waitFor(() => expect(simular).toHaveBeenCalledWith({ umbrales: { "confianza.medicamento_dosis": 0.98 }, ampliaciones: { alto_riesgo: [], control_especial: [], hallazgos_criticos: [] } }, undefined));
    const resultado = await screen.findByTestId("simulacion");
    expect(resultado).toHaveTextContent(/1 de 10/);
    expect(resultado).toHaveTextContent("REC-1");
    expect(resultado).toHaveTextContent("EN_REVISION_HUMANA");
    // proponer exige usuario y motivo (RN-L4)
    const boton = screen.getByRole("button", { name: /proponer versión/i });
    expect(boton).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/firmo como/i), "gestor.ana");
    await userEvent.type(screen.getByLabelText(/motivo de la versión/i), "cero errores de dosis");
    await userEvent.click(boton);
    await waitFor(() => expect(proponer).toHaveBeenCalledWith({
      cambios: { umbrales: { "confianza.medicamento_dosis": 0.98 }, ampliaciones: { alto_riesgo: [], control_especial: [], hallazgos_criticos: [] } },
      usuario: "gestor.ana", rol: "gestor", motivo: "cero errores de dosis",
    }));
  }, 15_000);

  it("lista las propuestas pendientes con sus aprobaciones y permite aprobar (RN-L5)", async () => {
    const aprobar = vi.spyOn(api, "aprobarConfiguracion").mockResolvedValue({ ...CONFIGURACION.propuestas[0], estado: "vigente" } as never);
    render(<AppRouter rutaInicial="/configuracion" rolInicial="gestor" />);
    const propuesta = await screen.findByTestId("propuesta-7");
    expect(propuesta).toHaveTextContent("1 de 2");
    expect(propuesta).toHaveTextContent(/toca seguridad/i);
    expect(propuesta).toHaveTextContent("gestor.luis");
    await userEvent.type(screen.getByLabelText(/firmo como/i), "gestor.ana");
    await userEvent.click(within(propuesta).getByRole("button", { name: /aprobar/i }));
    await waitFor(() => expect(aprobar).toHaveBeenCalledWith(7, { usuario: "gestor.ana", rol: "gestor" }));
    expect(screen.getByTestId("historial")).toHaveTextContent("reemplazada");
  });
});

describe("Métricas (RN-R1, RN-R4)", () => {
  it("muestra los indicadores y el aviso que propone subir el umbral", async () => {
    render(<AppRouter rutaInicial="/metricas" rolInicial="gestor" />);
    expect(await screen.findByTestId("kpi-automatizacion")).toHaveTextContent("67");
    expect(screen.getByTestId("kpi-acuse")).toHaveTextContent("3,2");
    const aviso = screen.getByTestId("avisos");
    expect(aviso).toHaveTextContent("RN-R4");
    expect(aviso).toHaveTextContent("0.97");
    expect(screen.getByTestId("por-motivo")).toHaveTextContent("campo dudoso");
    expect(screen.getByTestId("versiones")).toHaveTextContent("gpt-4.1-mini");
    expect(within(aviso).getByRole("link", { name: /configuración/i })).toHaveAttribute("href", "/configuracion");
  });
});

describe("Administración (RN-K, RN-S3)", () => {
  it("lista usuarios, crea uno nuevo y desactiva (RN-K4)", async () => {
    const crear = vi.spyOn(api, "crearUsuario").mockResolvedValue({ ...USUARIOS[0], usuario: "jefe.rojas", rol: "jefe_urgencias" } as never);
    const cambiar = vi.spyOn(api, "cambiarEstadoUsuario").mockResolvedValue({ ...USUARIOS[0], activo: false } as never);
    render(<AppRouter rutaInicial="/administracion" rolInicial="administrador" />);
    const filas = await screen.findAllByTestId("fila-usuario");
    expect(filas).toHaveLength(2);
    expect(filas[1]).toHaveTextContent(/servicio/i);
    expect(filas[1]).toHaveTextContent(/inactivo/i);
    await userEvent.type(screen.getByLabelText(/firmo como/i), "admin.root");
    await userEvent.type(screen.getByLabelText(/nombre de usuario/i), "jefe.rojas");
    await userEvent.type(screen.getByLabelText(/nombre completo/i), "Andrés Rojas");
    await userEvent.selectOptions(screen.getByLabelText(/rol del usuario/i), "jefe_urgencias");
    await userEvent.click(screen.getByRole("button", { name: /crear usuario/i }));
    await waitFor(() => expect(crear).toHaveBeenCalledWith({ usuario: "jefe.rojas", nombre: "Andrés Rojas", rol: "jefe_urgencias", tipo: "persona", actor: "admin.root" }));
    await userEvent.click(within(filas[0]).getByRole("button", { name: /desactivar/i }));
    await waitFor(() => expect(cambiar).toHaveBeenCalledWith("aud.ana", false, "admin.root"));
  });

  it("muestra la lista de puesta en marcha, la ficha del pack y los accesos", async () => {
    render(<AppRouter rutaInicial="/administracion" rolInicial="administrador" />);
    const puesta = await screen.findByTestId("puesta-en-marcha");
    expect(puesta).toHaveTextContent("2 de 4");
    expect(puesta).toHaveTextContent(/jefe de urgencias/i);
    expect(screen.getByTestId("pack")).toHaveTextContent("RETHUS");
    expect(screen.getByTestId("pack")).toHaveTextContent("15 años");
    expect(await screen.findByTestId("accesos")).toHaveTextContent("aud.ana");
  });

  it("el administrador no entra a configuración ni a documentos (RN-K2)", async () => {
    render(<AppRouter rutaInicial="/configuracion" rolInicial="administrador" />);
    expect(await screen.findByText(/sin acceso para este rol/i)).toBeInTheDocument();
  });
});
