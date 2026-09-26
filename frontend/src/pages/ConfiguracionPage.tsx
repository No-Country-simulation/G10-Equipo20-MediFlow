import { useEffect, useMemo, useState } from "react";

import { aprobarConfiguracion, ErrorApi, obtenerConfiguracion, proponerConfiguracion, rechazarConfiguracion, simularConfiguracion } from "../api";
import { useUsuario } from "../app/usuario";
import type { Ampliaciones, CambiosConfiguracion, Configuracion, Simulacion, VersionConfiguracion } from "../types";

interface DefUmbral {
  clave: string;
  etiqueta: string;
  grupo: "Confianza" | "Consistencia" | "Tiempos";
  unidad: string;
  regla: string;
  paso: number;
}

/** Sección 7 del documento de reglas: los configurables, con la regla que los usa. */
export const UMBRALES: DefUmbral[] = [
  { clave: "confianza.clasificacion", etiqueta: "Confianza de clasificación", grupo: "Confianza", unidad: "", regla: "RN-B4", paso: 0.01 },
  { clave: "confianza.identidad_paciente", etiqueta: "Confianza de identidad del paciente", grupo: "Confianza", unidad: "", regla: "RN-A4", paso: 0.01 },
  { clave: "confianza.medicamento_dosis", etiqueta: "Confianza de medicamento y dosis", grupo: "Confianza", unidad: "", regla: "RN-C3", paso: 0.01 },
  { clave: "confianza.diagnostico_codigo", etiqueta: "Confianza de diagnóstico y código", grupo: "Confianza", unidad: "", regla: "RN-C3", paso: 0.01 },
  { clave: "confianza.profesional", etiqueta: "Confianza del profesional", grupo: "Confianza", unidad: "", regla: "RN-A8", paso: 0.01 },
  { clave: "confianza.resto", etiqueta: "Confianza del resto de campos", grupo: "Confianza", unidad: "", regla: "RN-C3", paso: 0.01 },
  { clave: "consistencia.tolerancia_edad_anios", etiqueta: "Tolerancia documento-edad", grupo: "Consistencia", unidad: "años", regla: "RN-CO2", paso: 1 },
  { clave: "tiempos.comunicacion_critico_min", etiqueta: "Comunicación de un caso Crítico", grupo: "Tiempos", unidad: "min", regla: "RN-D1", paso: 1 },
  { clave: "tiempos.escalamiento_sin_acuse_min", etiqueta: "Escalamiento sin acuse", grupo: "Tiempos", unidad: "min", regla: "RN-F2", paso: 1 },
  { clave: "tiempos.atencion_urgente_h", etiqueta: "Atención de un caso Urgente", grupo: "Tiempos", unidad: "h", regla: "RN-D6", paso: 1 },
  { clave: "tiempos.cola_revision.critico_min", etiqueta: "Cola de revisión: Crítico", grupo: "Tiempos", unidad: "min", regla: "RN-J2", paso: 1 },
  { clave: "tiempos.cola_revision.urgente_h", etiqueta: "Cola de revisión: Urgente", grupo: "Tiempos", unidad: "h", regla: "RN-J2", paso: 1 },
  { clave: "tiempos.cola_revision.rutina_h_habiles", etiqueta: "Cola de revisión: Rutina", grupo: "Tiempos", unidad: "h hábiles", regla: "RN-J2", paso: 1 },
];

const NEWS2: Record<string, string> = {
  fr_bajo: "FR crítica baja (≤)", fr_alto: "FR crítica alta (≥)", spo2_bajo: "SpO2 crítica, escala 1 (≤)", spo2_escala2_min: "SpO2 escala 2, mínimo",
  spo2_escala2_max: "SpO2 escala 2, máximo", fc_bajo: "FC crítica baja (≤)", fc_alto: "FC crítica alta (≥)", pas_bajo: "PAS crítica (≤)",
  total_critico: "NEWS2 total crítico (≥)", edad_minima: "Edad mínima para NEWS2",
};

export function etiquetaUmbral(clave: string): string {
  return UMBRALES.find((u) => u.clave === clave)?.etiqueta ?? clave;
}

function resumenCambios(c: Partial<CambiosConfiguracion>): string[] {
  const salida = Object.entries(c.umbrales ?? {}).map(([k, v]) => `${etiquetaUmbral(k)} → ${v}`);
  const a = c.ampliaciones;
  if (a?.alto_riesgo?.length) salida.push(`+ alto riesgo: ${a.alto_riesgo.join(", ")}`);
  if (a?.control_especial?.length) salida.push(`+ control especial: ${a.control_especial.join(", ")}`);
  if (a?.hallazgos_criticos?.length) salida.push(`+ hallazgos críticos: ${a.hallazgos_criticos.map((h) => h.concepto).join(", ")}`);
  return salida;
}

function separar(texto: string): string[] {
  return texto.split(",").map((x) => x.trim()).filter(Boolean);
}

/** Configuración del gestor (RN-L1 a RN-L6). Quien configura no revisa (RN-K2). */
export function ConfiguracionPage() {
  const [cfg, setCfg] = useState<Configuracion | null>(null);
  const [textos, setTextos] = useState<Record<string, string>>({});
  const [altoRiesgo, setAltoRiesgo] = useState("");
  const [controlEspecial, setControlEspecial] = useState("");
  const [hallazgo, setHallazgo] = useState({ concepto: "", sinonimos: "", cie10: "" });
  const [usuario, setUsuario] = useUsuario();
  const [motivo, setMotivo] = useState("");
  const [simulacion, setSimulacion] = useState<Simulacion | null>(null);
  const [simulando, setSimulando] = useState(false);
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [motivosRechazo, setMotivosRechazo] = useState<Record<number, string>>({});

  const cargar = () =>
    obtenerConfiguracion()
      .then((c) => {
        setCfg(c);
        setTextos(Object.fromEntries(Object.entries(c.rangos).map(([k, r]) => [k, String(r.efectivo)])));
      })
      .catch(() => setMensaje("No hay conexión con la API."));
  useEffect(() => { cargar(); }, []);

  const cambios: CambiosConfiguracion = useMemo(() => {
    const umbrales: Record<string, number> = {};
    for (const [clave, texto] of Object.entries(textos)) {
      const valor = Number(texto);
      const rango = cfg?.rangos[clave];
      if (rango && Number.isFinite(valor) && texto.trim() !== "" && valor !== rango.efectivo) umbrales[clave] = valor;
    }
    const ampliaciones: Ampliaciones = {
      alto_riesgo: separar(altoRiesgo),
      control_especial: separar(controlEspecial),
      hallazgos_criticos: hallazgo.concepto.trim()
        ? [{ concepto: hallazgo.concepto.trim(), sinonimos: separar(hallazgo.sinonimos), cie10: separar(hallazgo.cie10), cie11: [] }]
        : [],
    };
    return { umbrales, ampliaciones };
  }, [textos, cfg, altoRiesgo, controlEspecial, hallazgo]);

  const hayCambios = Object.keys(cambios.umbrales).length > 0 || cambios.ampliaciones.alto_riesgo.length > 0
    || cambios.ampliaciones.control_especial.length > 0 || cambios.ampliaciones.hallazgos_criticos.length > 0;
  const fueraDeRango = Object.entries(cambios.umbrales).filter(([k, v]) => {
    const r = cfg?.rangos[k];
    return r && (v < r.min || v > r.max || (r.solo_a_la_baja && v > r.base));
  }).map(([k]) => k);
  const yo = usuario.trim();
  const actor = { usuario: yo, rol: "gestor" };

  function informar(e: unknown, fallback: string) {
    setMensaje(e instanceof ErrorApi ? `${e.status}: ${e.detalle}` : fallback);
  }

  async function simular() {
    setSimulando(true);
    setMensaje(null);
    try {
      setSimulacion(await simularConfiguracion(cambios, undefined));
    } catch (e) {
      informar(e, "No hay conexión con la API.");
    } finally {
      setSimulando(false);
    }
  }

  async function proponer() {
    setMensaje(null);
    try {
      const v = await proponerConfiguracion({ cambios, usuario: yo, rol: "gestor", motivo: motivo.trim() });
      setMensaje(`Propuesta #${v.id} creada. ${v.toca_seguridad ? "Toca seguridad: necesita dos aprobadores (RN-L5)." : "Necesita una aprobación."}`);
      setMotivo("");
      setAltoRiesgo("");
      setControlEspecial("");
      setHallazgo({ concepto: "", sinonimos: "", cie10: "" });
      setSimulacion(null);
      cargar();
    } catch (e) {
      informar(e, "No hay conexión con la API.");
    }
  }

  async function aprobar(v: VersionConfiguracion) {
    if (v.id == null) return;
    setMensaje(null);
    try {
      const r = await aprobarConfiguracion(v.id, actor);
      setMensaje(r.estado === "vigente" ? `Versión ${r.numero} vigente desde ahora. No es retroactiva (RN-L4).` : `Aprobación registrada: ${r.aprobaciones?.length ?? 0} de ${r.aprobaciones_requeridas}.`);
      cargar();
    } catch (e) {
      informar(e, "No hay conexión con la API.");
    }
  }

  async function rechazar(v: VersionConfiguracion) {
    if (v.id == null) return;
    setMensaje(null);
    try {
      await rechazarConfiguracion(v.id, { ...actor, motivo: motivosRechazo[v.id] ?? "" });
      setMensaje(`Propuesta #${v.id} rechazada.`);
      cargar();
    } catch (e) {
      informar(e, "No hay conexión con la API.");
    }
  }

  const grupos: DefUmbral["grupo"][] = ["Confianza", "Consistencia", "Tiempos"];

  return (
    <>
      <header className="encabezado">
        <div>
          <h1>Configuración</h1>
          <p className="sub">
            Umbrales dentro de rango (RN-L1). Cada cambio es una versión con autor, fecha y vigencia, y no es retroactiva (RN-L4).
            Antes de activarla, la simulación muestra qué habría cambiado sobre los últimos {cfg?.calidad.simulacion_ultimos ?? 50} documentos (RN-L6).
          </p>
        </div>
        <label style={{ minWidth: 240 }}>
          Gestor que firma
          <input value={usuario} onChange={(e) => setUsuario(e.target.value)} placeholder="gestor.ana" />
        </label>
      </header>
      {mensaje && <p className="estado-carga" role="status">{mensaje}</p>}

      <div className="dos-columnas">
        <section className="tarjeta">
          <h2>Umbrales configurables</h2>
          <p className="muted">Versión vigente: {cfg?.vigente.numero === 0 ? "valores iniciales de la sección 7" : `#${cfg?.vigente.numero} por ${cfg?.vigente.autor}`}. Fondo verde: lo que cambiaste.</p>
          <table className="umbrales">
            <thead><tr><th>Umbral</th><th>Rango</th><th>Nuevo valor</th></tr></thead>
            <tbody>
              {grupos.map((grupo) => (
                <FragmentoGrupo key={grupo} grupo={grupo} cfg={cfg} textos={textos} setTextos={setTextos} cambios={cambios} />
              ))}
            </tbody>
          </table>
          {fueraDeRango.length > 0 && <p className="error">Fuera de rango (RN-L1): {fueraDeRango.map(etiquetaUmbral).join(", ")}</p>}
        </section>

        <div>
          <section className="tarjeta" data-testid="no-configurable">
            <h2>No configurable (RN-L2)</h2>
            <p className="muted">Umbrales NEWS2 de guía clínica, seudonimización y separación de funciones. Se muestran, no se editan (RN-D5).</p>
            <table className="umbrales">
              <tbody>
                {Object.entries(cfg?.no_configurable.news2 ?? {}).map(([k, v]) => (
                  <tr key={k}><td>{NEWS2[k] ?? k}</td><td className="num"><strong>{v}</strong></td></tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="tarjeta" style={{ marginTop: 12 }}>
            <h2>Listas solo ampliables (RN-L3)</h2>
            <p className="muted">Se puede agregar, nunca quitar los de base. Separa con comas.</p>
            <ListaAmpliable testid="lista-alto_riesgo" titulo="Medicamentos de alto riesgo (RN-E6)" base={cfg?.listas.alto_riesgo.base ?? []} ampliadas={cfg?.listas.alto_riesgo.ampliadas ?? []} valor={altoRiesgo} onChange={setAltoRiesgo} />
            <ListaAmpliable testid="lista-control_especial" titulo="Control especial (RN-CO9)" base={cfg?.listas.control_especial.base ?? []} ampliadas={cfg?.listas.control_especial.ampliadas ?? []} valor={controlEspecial} onChange={setControlEspecial} />
            <div data-testid="lista-hallazgos_criticos">
              <h3 style={{ margin: "10px 0 4px" }}>Hallazgos críticos (RN-D2)</h3>
              <div className="chips-lectura">
                {(cfg?.listas.hallazgos_criticos.base ?? []).map((x) => <span key={x} className="chip">{x}</span>)}
                {(cfg?.listas.hallazgos_criticos.ampliados ?? []).map((x) => <span key={x} className="chip nuevo">{x}</span>)}
              </div>
              <div className="formulario">
                <label>Concepto nuevo<input value={hallazgo.concepto} onChange={(e) => setHallazgo({ ...hallazgo, concepto: e.target.value })} placeholder="TAPONAMIENTO_CARDIACO" /></label>
                <label>Sinónimos<input value={hallazgo.sinonimos} onChange={(e) => setHallazgo({ ...hallazgo, sinonimos: e.target.value })} placeholder="taponamiento cardiaco" /></label>
                <label>CIE-10<input value={hallazgo.cie10} onChange={(e) => setHallazgo({ ...hallazgo, cie10: e.target.value })} placeholder="I31.9" /></label>
              </div>
            </div>
          </section>
        </div>
      </div>

      <section className="tarjeta" style={{ marginTop: 12 }}>
        <h2>Simular y proponer</h2>
        <div className="acciones" style={{ alignItems: "end", flexWrap: "wrap", gap: 10 }}>
          <button type="button" className="secundario" disabled={!hayCambios || fueraDeRango.length > 0 || simulando} onClick={simular}>
            {simulando ? "Simulando…" : "Simular sobre los últimos documentos"}
          </button>
          <label style={{ flex: 1, minWidth: 260 }}>
            Motivo de la versión
            <input value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="cero errores de dosis pasan solos (sección 8)" />
          </label>
          <button type="button" disabled={!hayCambios || fueraDeRango.length > 0 || !yo || !motivo.trim()} onClick={proponer}>Proponer versión</button>
        </div>
        {hayCambios && <p className="muted" style={{ marginTop: 8 }}>Cambios: {resumenCambios(cambios).join(" · ")}</p>}
        {simulacion && <ResultadoSimulacion s={simulacion} />}
      </section>

      <section className="tarjeta" style={{ marginTop: 12 }}>
        <h2>Propuestas pendientes</h2>
        {cfg && cfg.propuestas.length === 0 && <p className="muted">No hay propuestas por aprobar.</p>}
        {cfg?.propuestas.map((v) => (
          <article key={v.id ?? 0} className="panel" data-testid={`propuesta-${v.id}`} style={{ marginTop: 8 }}>
            <div className="panel-cabecera">
              <strong>Propuesta #{v.id}</strong> · {v.autor} · {v.creado_en ? new Date(v.creado_en).toLocaleString("es-CO") : ""}
              {v.toca_seguridad && <span className="tag urgente" style={{ marginLeft: 8 }}>Toca seguridad · 2 aprobadores (RN-L5)</span>}
            </div>
            <p style={{ margin: "6px 0" }}>{v.motivo}</p>
            <ul className="accesos">{resumenCambios(v.cambios).map((c) => <li key={c}>{c}</li>)}</ul>
            {v.simulacion && (
              <p className="muted">Simulación: {v.simulacion.cambian} de {v.simulacion.documentos_evaluados} documentos cambiarían
                ({v.simulacion.mas_a_revision} más a revisión, {v.simulacion.mas_automaticos} más automáticos); {v.simulacion.sin_propuesta} sin propuesta del LLM.</p>
            )}
            <p><strong>{v.aprobaciones?.length ?? 0} de {v.aprobaciones_requeridas} aprobaciones</strong>{(v.aprobaciones?.length ?? 0) > 0 && <span className="muted"> · {v.aprobaciones?.map((a) => a.usuario).join(", ")}</span>}</p>
            <div className="acciones" style={{ gap: 8, flexWrap: "wrap" }}>
              <button type="button" disabled={!yo} onClick={() => aprobar(v)}>Aprobar</button>
              <label>
                <span className="oculto-visual">Motivo del rechazo de la propuesta {v.id}</span>
                <input value={motivosRechazo[v.id ?? 0] ?? ""} placeholder="Motivo del rechazo" onChange={(e) => setMotivosRechazo({ ...motivosRechazo, [v.id ?? 0]: e.target.value })} />
              </label>
              <button type="button" className="secundario" disabled={!yo} onClick={() => rechazar(v)}>Rechazar</button>
            </div>
          </article>
        ))}
      </section>

      <section className="tarjeta" style={{ marginTop: 12, padding: 0 }} data-testid="historial">
        <div style={{ padding: "12px 14px 0" }}><h2>Historial de versiones (RN-L4)</h2></div>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Versión</th><th>Autor</th><th>Cambios</th><th>Vigencia</th><th>Estado</th></tr></thead>
            <tbody>
              {cfg?.historial.map((v) => (
                <tr key={v.id ?? 0} className="fila rutina">
                  <td>{v.numero != null ? `#${v.numero}` : "—"}<span className="secundaria">{v.motivo}</span></td>
                  <td>{v.autor}<span className="secundaria">{v.aprobaciones?.map((a) => a.usuario).join(", ")}</span></td>
                  <td>{resumenCambios(v.cambios).join(" · ") || "—"}</td>
                  <td>{v.vigente_desde ? new Date(v.vigente_desde).toLocaleString("es-CO") : "—"}{v.vigente_hasta ? ` → ${new Date(v.vigente_hasta).toLocaleString("es-CO")}` : ""}</td>
                  <td><span className={`tag ${v.estado === "vigente" ? "exito" : v.estado === "rechazada" ? "critico" : "rutina"}`}>{v.estado}</span></td>
                </tr>
              ))}
              {cfg && cfg.historial.length === 0 && <tr><td colSpan={5} className="muted" style={{ textAlign: "center", padding: 20 }}>Sin versiones todavía: rigen los valores iniciales de la sección 7.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function FragmentoGrupo({ grupo, cfg, textos, setTextos, cambios }: {
  grupo: DefUmbral["grupo"]; cfg: Configuracion | null; textos: Record<string, string>;
  setTextos: (t: Record<string, string>) => void; cambios: CambiosConfiguracion;
}) {
  const filas = UMBRALES.filter((u) => u.grupo === grupo && cfg?.rangos[u.clave]);
  if (filas.length === 0) return null;
  return (
    <>
      <tr><th colSpan={3} style={{ background: "var(--superficie-2)" }}>{grupo}</th></tr>
      {filas.map((u) => {
        const r = cfg!.rangos[u.clave];
        const id = `umbral-${u.clave.replace(/\./g, "-")}`;
        return (
          <tr key={u.clave} className={u.clave in cambios.umbrales ? "cambiado" : ""}>
            <td><label htmlFor={id}>{u.etiqueta}</label><span className="secundaria">{u.regla}{r.efectivo !== r.base ? ` · base ${r.base}` : ""}</span></td>
            <td className="rango">{r.min} – {r.max} {u.unidad}{r.solo_a_la_baja ? " · solo a la baja" : ""}</td>
            <td className="num">
              <input id={id} type="number" step={u.paso} min={r.min} max={r.max} value={textos[u.clave] ?? ""} onChange={(e) => setTextos({ ...textos, [u.clave]: e.target.value })} />
            </td>
          </tr>
        );
      })}
    </>
  );
}

function ListaAmpliable({ testid, titulo, base, ampliadas, valor, onChange }: { testid: string; titulo: string; base: string[]; ampliadas: string[]; valor: string; onChange: (v: string) => void }) {
  return (
    <div data-testid={testid}>
      <h3 style={{ margin: "10px 0 4px" }}>{titulo}</h3>
      <div className="chips-lectura">
        {base.map((x) => <span key={x} className="chip">{x}</span>)}
        {ampliadas.map((x) => <span key={x} className="chip nuevo">{x}</span>)}
      </div>
      <label>
        Agregar a {titulo.toLowerCase()}
        <input value={valor} onChange={(e) => onChange(e.target.value)} placeholder="dci1, dci2" />
      </label>
    </div>
  );
}

function ResultadoSimulacion({ s }: { s: Simulacion }) {
  return (
    <div data-testid="simulacion" style={{ marginTop: 10 }}>
      <p>
        <strong>{s.cambian} de {s.documentos_evaluados}</strong> documentos evaluados cambiarían de decisión
        ({s.mas_a_revision} más a revisión humana, {s.mas_automaticos} más automáticos). {s.sin_propuesta} no se pueden simular porque no tienen propuesta del LLM.
      </p>
      {s.detalle.length > 0 && (
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Documento</th><th>Estado</th><th>Prioridad</th><th>Motivo</th><th>Destino</th></tr></thead>
            <tbody>
              {s.detalle.map((f) => (
                <tr key={`${f.documento_id}-${f.version}`} className="fila rutina">
                  <td><code>{f.documento_id}</code><span className="secundaria">{f.tipo}</span></td>
                  <td>{f.estado_actual} → <strong>{f.estado_simulado}</strong></td>
                  <td>{f.prioridad_actual} → <strong>{f.prioridad_simulada}</strong></td>
                  <td>{f.motivo_actual ?? "—"} → <strong>{f.motivo_simulado ?? "—"}</strong></td>
                  <td>{f.destino_actual} → <strong>{f.destino_simulado}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
