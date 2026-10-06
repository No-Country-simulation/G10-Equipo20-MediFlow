import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { obtenerMetricas, obtenerReferencia, urlExportarReferencia } from "../api";
import { etiquetaEstado, etiquetaMotivo } from "../app/mensajes";
import { AvisoSistemaDegradado } from "../components/AvisoSistema";
import type { ConjuntoReferencia, Metricas } from "../types";
import { etiquetaUmbral } from "./ConfiguracionPage";

const PERIODOS = [7, 30, 90];
const VERSIONES: Record<string, string> = { modelo_llm: "Modelo LLM", version_prompt: "Versión del prompt", version_reglas: "Versión de reglas", pack: "Pack de país" };

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)} %`;
}

function num(v: number | null | undefined, digitos = 1): string {
  return v == null ? "—" : v.toLocaleString("es-CO", { maximumFractionDigits: digitos });
}

function legible(clave: string): string {
  return clave.replace(/_/g, " ");
}

/** Métricas del gestor: indicadores calculables desde el historial (RN-R1). Sin datos del paciente (RN-M4). */
export function MetricasPage() {
  const [dias, setDias] = useState(30);
  const [m, setM] = useState<Metricas | null>(null);
  const [referencia, setReferencia] = useState<ConjuntoReferencia | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let activo = true;
    obtenerReferencia().then((r) => activo && setReferencia(r)).catch(() => activo && setReferencia(null));
    return () => { activo = false; };
  }, []);

  useEffect(() => {
    let activo = true;
    obtenerMetricas(dias).then((r) => activo && setM(r)).catch(() => activo && setError("No hay conexión con la API."));
    return () => { activo = false; };
  }, [dias]);

  const acuse = m?.acuse_criticos;
  const degradado = (m?.revision_por_motivo.fallo_tecnico?.porcentaje ?? 0) >= 0.5;
  const fn = m?.falsos_negativos_criticos;

  return (
    <>
      <header className="encabezado">
        <div>
          <h1>Métricas</h1>
          <p className="sub">Indicadores calculados del historial. Cada documento registra modelo, prompt, reglas y pack, y su costo en tokens.</p>
        </div>
        <div className="pestanas" role="group" aria-label="Periodo">
          {PERIODOS.map((p) => (
            <button key={p} type="button" aria-pressed={dias === p} className={dias === p ? "" : "secundario"} onClick={() => setDias(p)}>{p} días</button>
          ))}
        </div>
      </header>
      {error && <p className="error">{error}</p>}

      {m && (m.revision_por_motivo.fallo_tecnico?.porcentaje ?? 0) >= 0.5 && (
        <AvisoSistemaDegradado titulo="El motor de extracción no está respondiendo.">
          <p>{pct(m.revision_por_motivo.fallo_tecnico.porcentaje)} de los documentos del periodo pasó a revisión manual por fallo técnico. La tasa de automatización y los falsos negativos no son representativos hasta que el motor vuelva.</p>
        </AvisoSistemaDegradado>
      )}
      <div className="kpis">
        <div className="tarjeta kpi" data-testid="kpi-automatizacion"><span className={`n ${degradado ? "no-representativo" : ""}`}>{pct(m?.tasa_automatizacion)}</span><span className="muted">tasa de automatización · {m?.procesados ?? "—"} procesados{degradado && " · no representativo"}</span></div>
        <div className="tarjeta kpi" data-testid="kpi-acuse"><span className={`n ${acuse && acuse.pendientes > 0 ? "critico" : ""}`}>{acuse?.minutos_promedio == null ? "sin acuses" : `${num(acuse.minutos_promedio)} min`}</span><span className="muted">hasta el acuse en críticos · {acuse?.dentro_de_plazo ?? 0} de {acuse?.acusadas ?? 0} dentro de {acuse?.plazo_min ?? 15} min · {acuse?.pendientes ?? 0} pendientes</span></div>
        <div className="tarjeta kpi" data-testid="kpi-falsos-negativos"><span className={`n ${fn && fn.n > 0 ? "critico" : degradado ? "no-representativo" : ""}`}>{fn?.n ?? "—"}</span><span className="muted">falsos negativos críticos · {pct(fn?.tasa)} de {fn?.criticos_totales ?? 0} críticos</span></div>
        <div className="tarjeta kpi" data-testid="kpi-tokens"><span className="n">{num((m?.tokens.entrada ?? 0) + (m?.tokens.salida ?? 0), 0)}</span><span className="muted">tokens · {num(m?.tokens.entrada, 0)} entrada / {num(m?.tokens.salida, 0)} salida</span></div>
        <div className="tarjeta kpi"><span className="n">{m?.documentos ?? "—"}</span><span className="muted">documentos en el periodo</span></div>
      </div>

      {m && m.avisos.length > 0 && (
        <section className="tarjeta aviso-tarjeta" data-testid="avisos" style={{ marginTop: 12 }}>
          <h2>Avisos al gestor</h2>
          <ul className="accesos">
            {m.avisos.map((a) => (
              <li key={a.campo}>
                {legible(a.campo)}: tasa de corrección {pct(a.tasa)} sobre un límite de {pct(a.limite)}.
                {" "}Se propone subir <strong>{etiquetaUmbral(a.umbral)}</strong> de {a.umbral_actual} a {a.umbral_propuesto}. <Link to="/configuracion">Ir a Configuración ›</Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="dos-columnas" style={{ marginTop: 12 }}>
        <section className="tarjeta" data-testid="por-motivo">
          <h2>Porcentaje a revisión por motivo</h2>
          <table className="umbrales">
            <thead><tr><th>Motivo</th><th>Documentos</th><th>% del total</th></tr></thead>
            <tbody>
              {Object.entries(m?.revision_por_motivo ?? {}).map(([motivo, v]) => (
                <tr key={motivo}><td>{etiquetaMotivo(motivo) || legible(motivo)}<span className="barra"><i style={{ width: `${Math.round(v.porcentaje * 100)}%` }} /></span></td><td className="num">{v.n}</td><td className="num">{pct(v.porcentaje)}</td></tr>
              ))}
              {m && Object.keys(m.revision_por_motivo).length === 0 && <tr><td colSpan={3} className="muted">Nada fue a revisión humana en el periodo.</td></tr>}
            </tbody>
          </table>
        </section>

        <section className="tarjeta" data-testid="por-etapa">
          <h2>Tiempo por etapa</h2>
          <table className="umbrales">
            <thead><tr><th>Transición</th><th>Promedio</th></tr></thead>
            <tbody>
              {Object.entries(m?.tiempo_por_etapa_s ?? {}).map(([etapa, s]) => (
                <tr key={etapa}><td>{etapa.split("→").map(etiquetaEstado).join(" → ")}</td><td className="num">{s >= 60 ? `${num(s / 60)} min` : `${num(s, 2)} s`}</td></tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <section className="tarjeta" style={{ marginTop: 12, padding: 0 }} data-testid="por-campo">
        <div style={{ padding: "12px 14px 0" }}><h2>Tasa de corrección por campo</h2><p className="muted">Límite {pct(m?.limite_correccion_campo)}. Sobre el límite se avisa y se propone subir el umbral del campo.</p></div>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Campo</th><th>Correcciones</th><th>Documentos revisados</th><th>Tasa</th><th>Umbral que lo gobierna</th></tr></thead>
            <tbody>
              {m?.correccion_por_campo.map((c) => (
                <tr key={c.campo} className={`fila ${c.supera_limite ? "supera" : "rutina"}`}>
                  <td><code>{c.campo}</code></td><td>{c.correcciones}</td><td>{c.documentos_revisados}</td>
                  <td>{pct(c.tasa)}{c.supera_limite && <span className="tag urgente" style={{ marginLeft: 6 }}>sobre el límite</span>}</td>
                  <td>{c.umbral_relacionado ? etiquetaUmbral(c.umbral_relacionado) : "—"}</td>
                </tr>
              ))}
              {m && m.correccion_por_campo.length === 0 && <tr><td colSpan={5} className="muted" style={{ textAlign: "center", padding: 20 }}>Sin correcciones humanas en el periodo.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="tarjeta" style={{ marginTop: 12, padding: 0 }} data-testid="referencia">
        <div style={{ padding: "12px 14px 0" }}>
          <h2>Conjunto de referencia <span className="muted" style={{ fontWeight: 400 }}>· {referencia?.resumen.casos ?? 0} caso{referencia?.resumen.casos === 1 ? "" : "s"} de {referencia?.resumen.documentos ?? 0} documento{referencia?.resumen.documentos === 1 ? "" : "s"}</span></h2>
          <p className="muted">
            Cada corrección humana entra seudonimizada: lo que vio el motor, lo que propuso y lo que la persona corrigió. Sirve para medir un cambio de modelo, prompt o reglas antes de sacarlo.
            {referencia && referencia.resumen.subidos_a_critico.length > 0 && <> <strong>{referencia.resumen.subidos_a_critico.length}</strong> documento{referencia.resumen.subidos_a_critico.length === 1 ? "" : "s"} que una persona subió a Crítico.</>}
            {referencia && referencia.resumen.casos > 0 && <> <a href={urlExportarReferencia()} download="conjunto_referencia.json">Descargar el conjunto completo (JSON)</a></>}
          </p>
        </div>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Documento</th><th>Campo</th><th>Leído → corregido</th><th>Prioridad</th><th>Quién</th></tr></thead>
            <tbody>
              {referencia?.casos.map((c) => (
                <tr key={c.id} data-testid="caso-referencia" className={`fila ${c.nivel_resultante === "Crítico" && c.nivel_antes !== "Crítico" ? "critico" : "rutina"}`}>
                  <td><code>{c.documento_id}</code><span className="secundaria">{c.tipo_documento ?? "sin tipo"} · {c.origen === "transcripcion" ? "transcripción" : "corrección"}</span></td>
                  <td><code>{c.campo}</code></td>
                  <td>{c.extraido == null ? <span className="muted">sin lectura</span> : <code>{String(c.extraido)}</code>} → <code>{String(c.corregido ?? "—")}</code></td>
                  <td>{c.nivel_antes ?? "—"}{c.nivel_resultante && c.nivel_resultante !== c.nivel_antes && <> → <strong>{c.nivel_resultante}</strong></>}</td>
                  <td>{c.usuario}<span className="secundaria">{c.creado_en ? new Date(c.creado_en).toLocaleDateString("es-CO") : ""}</span></td>
                </tr>
              ))}
              {referencia && referencia.casos.length === 0 && <tr><td colSpan={5} className="muted" style={{ textAlign: "center", padding: 20 }}>Todavía no hay correcciones humanas: el conjunto se llena solo con cada una.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <div className="dos-columnas" style={{ marginTop: 12 }}>
        <section className="tarjeta" data-testid="versiones">
          <h2>Versiones por documento</h2>
          {Object.entries(m?.versiones ?? {}).map(([tipo, valores]) => (
            <p key={tipo} style={{ margin: "4px 0" }}><strong>{VERSIONES[tipo] ?? legible(tipo)}:</strong> {Object.entries(valores).map(([k, n]) => `${k} (${n})`).join(" · ") || "—"}</p>
          ))}
        </section>
        <section className="tarjeta">
          <h2>Por estado y prioridad</h2>
          <p className="muted">{Object.entries(m?.por_estado ?? {}).map(([k, v]) => `${etiquetaEstado(k)}: ${v}`).join(" · ") || "—"}</p>
          <p className="muted">{Object.entries(m?.por_prioridad ?? {}).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—"}</p>
          {fn && fn.documentos.length > 0 && (
            <p className="muted">Falsos negativos críticos: {fn.documentos.map((d) => <Link key={d} to={`/documentos/${encodeURIComponent(d)}`} style={{ marginRight: 6 }}>{d}</Link>)}</p>
          )}
        </section>
      </div>
    </>
  );
}
