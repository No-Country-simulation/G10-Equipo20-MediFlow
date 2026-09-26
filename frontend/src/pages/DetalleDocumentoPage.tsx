import { Check, Pencil, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { colaRevision, confirmarEntrega, consultarDocumento, ErrorApi, resolverRevision, urlOriginal, urlVistaPrevia } from "../api";
import { etiquetaConcepto, etiquetaEstado, etiquetaMotivo, motivoLegible } from "../app/mensajes";
import { calcularPlazo, PLAZO_ACUSE_MIN } from "../app/plazos";
import { useRol } from "../app/RolContext";
import { enmascarar, useUsuario } from "../app/usuario";
import { HistorialDecisiones } from "../components/HistorialDecisiones";
import { AccionAcuse } from "../components/AccionAcuse";
import { TagEstado, TagPrioridad } from "../components/Tags";
import type { AccionRevision, DocumentoDetalle, ItemCola } from "../types";

type ClaveConfianza = "identidad_paciente" | "medicamento_dosis" | "diagnostico_codigo" | "profesional";

interface Correccion {
  campo: string;
  valor: string;
}

function PildoraConfianza({ valor, umbral }: { valor: number | null | undefined; umbral: number | undefined }) {
  if (valor === null || valor === undefined) return <span className="tag neutro">sin dato</span>;
  const bajo = umbral !== undefined && valor < umbral;
  return <span className={`tag ${bajo ? "urgente" : "exito"}`} title="Confianza del LLM (RN-C3)">{valor.toFixed(2)}</span>;
}

export function DetalleDocumentoPage() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const desdeCola = params.get("cola") === "1";
  const navigate = useNavigate();
  const { rol, modoDiscreto, alternarModoDiscreto } = useRol();
  const [usuario] = useUsuario();

  const [detalle, setDetalle] = useState<DocumentoDetalle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pagina, setPagina] = useState(1);
  const [textoOriginal, setTextoOriginal] = useState<string | null>(null);
  const [cola, setCola] = useState<ItemCola[]>([]);
  const [motivo, setMotivo] = useState("");
  const [correccion, setCorreccion] = useState<Correccion | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [entregas, setEntregas] = useState<Record<string, boolean>>({});
  const [pendientes, setPendientes] = useState<string[] | null>(null);
  const [ahora, setAhora] = useState(() => new Date());

  const cargar = useCallback(() => {
    consultarDocumento(id)
      .then((d) => { setDetalle(d); setEntregas(d.entregas ?? {}); setError(null); })
      .catch((e) => setError(e instanceof ErrorApi ? e.detalle : "No hay conexión con la API."));
  }, [id]);

  useEffect(() => { setPagina(1); setCorreccion(null); setMensaje(null); setPendientes(null); cargar(); }, [cargar]);
  useEffect(() => {
    if (desdeCola) colaRevision().then(setCola).catch(() => setCola([]));
  }, [desdeCola]);
  useEffect(() => {
    const reloj = setInterval(() => setAhora(new Date()), 15_000);
    return () => clearInterval(reloj);
  }, []);
  useEffect(() => {
    if (!detalle || detalle.formato !== "txt") { setTextoOriginal(null); return; }
    let activo = true;
    fetch(urlOriginal(detalle.documento_id)).then((r) => (r.ok ? r.text() : Promise.reject(new Error("sin original")))).then((t) => activo && setTextoOriginal(t)).catch(() => activo && setTextoOriginal(null));
    return () => { activo = false; };
  }, [detalle]);

  const r = detalle?.resultado ?? null;
  const enRevision = detalle?.estado === "EN_REVISION_HUMANA";
  const posicionCola = useMemo(() => cola.findIndex((c) => c.documento_id === id), [cola, id]);

  const irA = useCallback((desplazamiento: number) => {
    if (posicionCola < 0) return;
    const destino = cola[posicionCola + desplazamiento];
    if (destino) navigate(`/documentos/${encodeURIComponent(destino.documento_id)}?cola=1`);
  }, [cola, posicionCola, navigate]);

  const resolver = useCallback(async (accion: AccionRevision, correcciones?: Record<string, unknown>) => {
    if (!detalle || !usuario.trim() || enviando) return;
    if (accion === "rechazar" && !motivo.trim()) return;
    if (accion === "corregir" && !correcciones) return;
    setEnviando(true);
    setMensaje(null);
    try {
      const resp = await resolverRevision(detalle.documento_id, { accion, usuario: usuario.trim(), rol: rol.id, motivo, correcciones: correcciones ?? null });
      setMensaje(`${accion === "aprobar" ? "Aprobado" : accion === "corregir" ? "Corregido y re-evaluado" : "Rechazado"}. Queda en ${etiquetaEstado(resp.estado)}.`);
      setCorreccion(null);
      setMotivo("");
      cargar();
    } catch (e) {
      setMensaje(e instanceof ErrorApi ? `${e.status}: ${e.detalle}` : "No hay conexión con la API.");
    } finally {
      setEnviando(false);
    }
  }, [detalle, usuario, enviando, motivo, rol.id, cargar]);

  // Atajos del banco de trabajo: A aprobar, C corregir, R rechazar, J/K moverse en la cola.
  useEffect(() => {
    function alTeclear(e: KeyboardEvent) {
      const objetivo = e.target as HTMLElement | null;
      if (objetivo && ["INPUT", "TEXTAREA", "SELECT"].includes(objetivo.tagName)) return;
      const tecla = e.key.toLowerCase();
      if (tecla === "j") irA(1);
      else if (tecla === "k") irA(-1);
      else if (enRevision && tecla === "a") void resolver("aprobar");
      else if (enRevision && tecla === "r") void resolver("rechazar");
      else if (enRevision && tecla === "c") setCorreccion((c) => c ?? { campo: "", valor: "" });
    }
    window.addEventListener("keydown", alTeclear);
    return () => window.removeEventListener("keydown", alTeclear);
  }, [irA, resolver, enRevision]);

  async function entregar(destino: string) {
    if (!detalle) return;
    try {
      const resp = await confirmarEntrega(detalle.documento_id, destino);
      setEntregas(resp.entregas);
      setPendientes(resp.pendientes);
      if (resp.estado !== detalle.estado) cargar();
    } catch (e) {
      setMensaje(e instanceof ErrorApi ? `${e.status}: ${e.detalle}` : "No hay conexión con la API.");
    }
  }

  if (error) return <p className="error" style={{ marginTop: 16 }}>{error}</p>;
  if (!detalle) return <p className="muted" style={{ marginTop: 16 }}>Cargando…</p>;

  const ver = (valor: string | null | undefined) => (modoDiscreto ? enmascarar(valor) : valor ?? "—");
  const conf = detalle.confianzas ?? {};
  const umb = detalle.umbrales ?? {};
  const bajo = (clave: ClaveConfianza) => conf[clave] !== null && conf[clave] !== undefined && umb[clave] !== undefined && (conf[clave] as number) < (umb[clave] as number);
  const alerta = detalle.alerta;
  const plazoAlerta = alerta ? calcularPlazo(alerta.emitida_en, PLAZO_ACUSE_MIN, ahora) : null;
  const plan = r ? (enRevision ? r.enrutamiento.destinos_tras_revision : [r.enrutamiento.destino_principal, ...r.enrutamiento.destinos_secundarios]) : [];
  const retenidas = r?.enrutamiento.entregas_retenidas ?? {};
  const eventos = [
    ...(detalle.transiciones ?? []).map((t) => ({ fecha: t.fecha_hora, texto: `${etiquetaEstado(t.a_estado)} · ${t.actor}`, detalle: t.motivo, tipo: "estado" as const })),
    ...(alerta ? [{ fecha: alerta.emitida_en, texto: "Alerta crítica emitida", detalle: `${alerta.canal} → ${alerta.destinatario}`, tipo: "alerta" as const }] : []),
    ...(alerta?.acusado_por ? [{ fecha: alerta.emitida_en, texto: `Acuse de ${alerta.acusado_por}`, detalle: "circuito cerrado", tipo: "acuse" as const }] : []),
  ].sort((a, b) => a.fecha.localeCompare(b.fecha));

  return (
    <>
      <header className="encabezado banco-cabecera">
        <div>
          <p className="muted" style={{ margin: 0 }}>
            <Link to={desdeCola ? "/revision" : "/documentos"}>{desdeCola ? "Cola de revisión" : "Documentos"}</Link> / <code>{detalle.documento_id}</code>
            {desdeCola && posicionCola >= 0 && <> · {posicionCola + 1} de {cola.length} en la cola · <kbd>J</kbd> siguiente <kbd>K</kbd> anterior</>}
          </p>
          <div className="titulo-doc">
            <h1>{detalle.documento_id}</h1>
            <TagPrioridad nivel={detalle.nivel_prioridad} />
            <TagEstado estado={detalle.estado} />
          </div>
          <p className="sub">
            {r?.clasificacion.tipo ?? "Sin clasificar"} · {detalle.canal_origen?.replace("_", " ")} · versión {detalle.version}
            {detalle.nombre_archivo && <> · {detalle.nombre_archivo}</>}
            {r && r.extraccion.hallazgos_criticos_detectados.length > 0 && (
              <> · <span className="chips" style={{ display: "inline-flex" }}>{r.extraccion.hallazgos_criticos_detectados.map((h) => <span key={h} className="chip critico" title={h}>{etiquetaConcepto(h)}</span>)}</span></>
            )}
          </p>
        </div>
        {alerta && plazoAlerta && (
          <div className={`alerta-doc ${alerta.estado_acuse === "acusado" ? "acusada" : plazoAlerta.vencido ? "escalada" : ""}`} data-testid="alerta-documento">
            <strong>{alerta.estado_acuse === "acusado" ? `Alerta acusada por ${alerta.acusado_por}` : plazoAlerta.vencido ? "Alerta crítica escalada" : "Alerta crítica sin acuse"}</strong>
            <span className="muted">{alerta.canal} → {alerta.destinatario}{alerta.estado_acuse !== "acusado" && <> · <span className={`plazo ${plazoAlerta.vencido ? "vencido" : plazoAlerta.apremia ? "apremia" : ""}`}>{plazoAlerta.texto}</span></>}</span>
            {alerta.estado_acuse !== "acusado" && <AccionAcuse documentoId={detalle.documento_id} onAcusado={(resp) => { setMensaje(`Acuse registrado por ${resp.acusado_por}. Circuito cerrado.`); cargar(); }} />}
          </div>
        )}
      </header>

      {mensaje && <p className="estado-carga" role="status">{mensaje}</p>}

      <div className="banco">
        {/* ------------------------------------------------ Original */}
        <section className="panel" aria-labelledby="p-original">
          <div className="panel-cabecera">
            <h2 id="p-original">Original</h2>
            <label className="interruptor">
              <input type="checkbox" checked={modoDiscreto} onChange={alternarModoDiscreto} />
              Modo discreto
            </label>
          </div>
          {detalle.formato === "pdf" && (
            <>
              <div className="paginador">
                <button type="button" className="secundario" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>‹</button>
                <span>pág {pagina} / {detalle.num_paginas ?? 1}</span>
                <button type="button" className="secundario" disabled={pagina >= (detalle.num_paginas ?? 1)} onClick={() => setPagina(pagina + 1)}>›</button>
              </div>
              <img className={`vista-previa ${modoDiscreto ? "discreto" : ""}`} src={urlVistaPrevia(detalle.documento_id, pagina)} alt={`Página ${pagina} del original`} />
            </>
          )}
          {(detalle.formato === "png" || detalle.formato === "jpeg") && (
            <img className={`vista-previa ${modoDiscreto ? "discreto" : ""}`} src={urlOriginal(detalle.documento_id)} alt="Imagen original" />
          )}
          {detalle.formato === "txt" && (
            <pre className="texto-original">{textoOriginal === null ? "Original no disponible." : modoDiscreto ? (detalle.texto_enviado_llm ?? "") : textoOriginal}</pre>
          )}
          {modoDiscreto && detalle.formato !== "txt" && <p className="muted">Vista previa difuminada: datos del paciente ocultos en esta pantalla.</p>}
          <p><a href={urlOriginal(detalle.documento_id)} target="_blank" rel="noreferrer">Ver original</a></p>
          <details>
            <summary>Qué salió al LLM (texto seudonimizado)</summary>
            <pre className="texto-original">{detalle.texto_enviado_llm || "Sin texto: el documento se leyó como imagen."}</pre>
          </details>
        </section>

        {/* ------------------------------------------------ Extracción */}
        <section className="panel" aria-labelledby="p-extraccion">
          <div className="panel-cabecera"><h2 id="p-extraccion">Extracción</h2><span className="muted">confianza por campo</span></div>
          {!r ? <p className="muted">Sin resultado.</p> : (
            <>
              <dl className="campos-extraccion">
                <div data-testid="campo-identidad_paciente" className={bajo("identidad_paciente") ? "dudoso" : ""}>
                  <dt>Paciente</dt>
                  <dd><span>{ver(r.extraccion.paciente.nombre)}</span><span>· {r.extraccion.paciente.edad ?? "—"} años</span> <PildoraConfianza valor={conf.identidad_paciente} umbral={umb.identidad_paciente} /></dd>
                  <dd className="muted">Documento: {r.extraccion.paciente.documento.tipo} {r.extraccion.paciente.documento.valor ? ver(r.extraccion.paciente.documento.valor) : ""} ({r.extraccion.paciente.documento.estado})</dd>
                  {bajo("identidad_paciente") && <dd className="aviso">Bajo el umbral {umb.identidad_paciente?.toFixed(2)} <button type="button" className="enlace" onClick={() => setCorreccion({ campo: "extraccion.paciente.documento.valor", valor: r.extraccion.paciente.documento.valor ?? "" })}>Corregir</button></dd>}
                </div>
                <div data-testid="campo-diagnostico_codigo" className={bajo("diagnostico_codigo") ? "dudoso" : ""}>
                  <dt>Diagnósticos</dt>
                  {r.extraccion.diagnosticos.map((d, i) => (
                    <dd key={i}>{d.texto} <code>{d.cie10_sugerido ?? "—"}</code> {d.cie11_sugerido && <code>{d.cie11_sugerido}</code>} {i === 0 && <PildoraConfianza valor={conf.diagnostico_codigo} umbral={umb.diagnostico_codigo} />}</dd>
                  ))}
                  {r.extraccion.diagnosticos.length === 0 && <dd className="muted">ninguno</dd>}
                  {bajo("diagnostico_codigo") && <dd className="aviso">Bajo el umbral {umb.diagnostico_codigo?.toFixed(2)}{r.clasificacion.nivel_prioridad === "Crítico" && ": crítico con baja confianza, la alerta ya salió"} <button type="button" className="enlace" onClick={() => setCorreccion({ campo: "extraccion.diagnosticos[0].cie10_sugerido", valor: r.extraccion.diagnosticos[0]?.cie10_sugerido ?? "" })}>Corregir</button></dd>}
                </div>
                <div data-testid="campo-profesional" className={bajo("profesional") ? "dudoso" : ""}>
                  <dt>Profesional</dt>
                  <dd><span>{ver(r.extraccion.profesional.nombre)}</span><span>· {r.extraccion.profesional.registro_profesional ?? "sin registro"}</span> <PildoraConfianza valor={conf.profesional} umbral={umb.profesional} /></dd>
                  {bajo("profesional") && <dd className="aviso">Bajo el umbral {umb.profesional?.toFixed(2)} <button type="button" className="enlace" onClick={() => setCorreccion({ campo: "extraccion.profesional.registro_profesional", valor: r.extraccion.profesional.registro_profesional ?? "" })}>Corregir</button></dd>}
                </div>
                <div>
                  <dt>Fecha del documento</dt>
                  <dd>{r.extraccion.fecha_documento ?? "—"}</dd>
                </div>
                <div>
                  <dt>Signos vitales</dt>
                  <dd>FR {r.extraccion.signos_vitales.FR ?? "—"} · SpO2 {r.extraccion.signos_vitales.SpO2 ?? "—"} · FC {r.extraccion.signos_vitales.FC ?? "—"} · PAS {r.extraccion.signos_vitales.PAS ?? "—"} · T {r.extraccion.signos_vitales.Temp ?? "—"}</dd>
                  <dd><strong>NEWS2 total: {r.extraccion.signos_vitales.NEWS2_total ?? "no aplica"}</strong> <span className="muted">calculado por el sistema</span></dd>
                </div>
                <div data-testid="campo-medicamento_dosis" className={bajo("medicamento_dosis") ? "dudoso" : ""}>
                  <dt>Medicamentos</dt>
                  {r.extraccion.medicamentos.map((m, i) => (
                    <dd key={i}>{m.dci} {m.dosis ?? ""} {m.dosis_valor && <span className="muted">(leído {m.dosis_valor})</span>} {m.via ?? ""} {m.frecuencia ?? ""}
                      {m.alto_riesgo && <span className="chip critico"> alto riesgo</span>}{m.control_especial && <span className="chip urgente"> control especial</span>}
                      {i === 0 && <PildoraConfianza valor={conf.medicamento_dosis} umbral={umb.medicamento_dosis} />}
                    </dd>
                  ))}
                  {r.extraccion.medicamentos.length === 0 && <dd className="muted">ninguno</dd>}
                  {bajo("medicamento_dosis") && <dd className="aviso">Bajo el umbral {umb.medicamento_dosis?.toFixed(2)} <button type="button" className="enlace" onClick={() => setCorreccion({ campo: "extraccion.medicamentos[0].dosis", valor: r.extraccion.medicamentos[0]?.dosis ?? "" })}>Corregir</button></dd>}
                </div>
                <div>
                  <dt>Hallazgos críticos</dt>
                  <dd>{r.extraccion.hallazgos_criticos_detectados.length ? <span className="chips">{r.extraccion.hallazgos_criticos_detectados.map((h) => <span key={h} className="chip critico" title={h}>{etiquetaConcepto(h)}</span>)}</span> : <span className="muted">ninguno</span>}</dd>
                </div>
              </dl>
              <details className="tecnico">
                <summary>Detalle técnico: reglas disparadas ({r.historial_decisiones.length})</summary>
                <HistorialDecisiones historial={r.historial_decisiones} />
              </details>
            </>
          )}
        </section>

        {/* ------------------------------------------------ Decisión */}
        <section className="panel" aria-labelledby="p-decision">
          <div className="panel-cabecera"><h2 id="p-decision">Decisión</h2></div>
          <p className="muted firma" id="firma-decision">{usuario.trim() ? <>Firmas como <strong>{usuario.trim()}</strong> · {rol.nombre}</> : <>Para aprobar, corregir o rechazar, escribe tu usuario en <strong>Firmo como</strong>, en la barra lateral.</>}</p>

          {enRevision && r && (
            <>
              <p className="aviso">Requiere revisión: <strong>{etiquetaMotivo(r.evaluacion.motivo_auditoria)}</strong>{r.evaluacion.campos_dudosos.length > 0 && <> · dudosos: {r.evaluacion.campos_dudosos.join(", ")}</>}</p>
              {r.evaluacion.motivo_auditoria === "fallo_tecnico" && <p className="muted">El motor de extracción no leyó este documento. Revísalo contra el original y corrige los campos que falten.</p>}
              <p><span className="muted">Plan tras revisión:</span> {plan.join(" + ") || "—"}</p>
              <label>
                Motivo (obligatorio para rechazar o bajar la prioridad)
                <input value={motivo} onChange={(e) => setMotivo(e.target.value)} />
              </label>
              {correccion && (
                <div className="tarjeta correccion">
                  <SelectorCampo correccion={correccion} onChange={setCorreccion} />
                  <label>
                    Valor corregido
                    {correccion.campo === "nivel_prioridad" ? (
                      <select value={correccion.valor} onChange={(e) => setCorreccion({ ...correccion, valor: e.target.value })}>
                        <option value="">Elige la prioridad…</option>
                        <option value="Crítico">Crítico</option>
                        <option value="Urgente">Urgente</option>
                        <option value="Rutina">Rutina</option>
                      </select>
                    ) : (
                      <input value={correccion.valor} onChange={(e) => setCorreccion({ ...correccion, valor: e.target.value })} />
                    )}
                  </label>
                  <div className="acciones">
                    <button type="button" disabled={!usuario.trim() || !correccion.campo.trim()} onClick={() => resolver("corregir", { [correccion.campo.trim()]: correccion.valor })}>Aplicar corrección</button>
                    <button type="button" className="secundario" onClick={() => setCorreccion(null)}>Cancelar</button>
                  </div>
                  <p className="muted">Las reglas se vuelven a aplicar sin llamar otra vez al LLM, y queda registrado el valor leído y el corregido.</p>
                </div>
              )}
              <div className="acciones" style={{ marginTop: 8 }}>
                <button type="button" aria-describedby="firma-decision" disabled={!usuario.trim() || enviando} onClick={() => resolver("aprobar")}><Check size={16} aria-hidden="true" />Aprobar <kbd>A</kbd></button>
                <button type="button" className="secundario" disabled={!usuario.trim() || enviando} onClick={() => setCorreccion((c) => c ?? { campo: "", valor: "" })}><Pencil size={16} aria-hidden="true" />Corregir <kbd>C</kbd></button>
                <button type="button" className="peligro" disabled={!usuario.trim() || !motivo.trim() || enviando} onClick={() => resolver("rechazar")}><X size={16} aria-hidden="true" />Rechazar <kbd>R</kbd></button>
              </div>
            </>
          )}

          {!enRevision && r && detalle.estado !== "RECHAZADO" && (
            <>
              <h3>Entregas</h3>
              <ul className="destinos">
                {plan.map((destino) => (
                  <li key={destino}>
                    <strong>{destino}</strong>
                    {r.enrutamiento.motivos_destino[destino] && <span className="muted"> · {r.enrutamiento.motivos_destino[destino]}</span>}
                    {retenidas[destino] ? <span className="aviso"> retenida: {retenidas[destino]}</span>
                      : entregas[destino] ? <span className="ok"> confirmada</span>
                      : detalle.estado === "ENRUTADO" && <button type="button" className="secundario" onClick={() => entregar(destino)}>Confirmar {destino}</button>}
                  </li>
                ))}
              </ul>
              {pendientes && pendientes.length > 0 && <p className="aviso">Pendiente para cerrar: {pendientes.join(", ")}</p>}
              {detalle.estado === "ENTREGADO" && <p className="ok">Entregado. Es el estado final.</p>}
              <p className="muted">{r.enrutamiento.justificacion_enrutamiento}</p>
            </>
          )}

          <h3 style={{ marginTop: 16 }}>Línea de tiempo</h3>
          <ol className="timeline">
            {eventos.map((e, i) => (
              <li key={i} data-testid="evento" className={e.tipo}>
                <span className="estado">{e.texto}</span>
                <span className="muted"> · {new Date(e.fecha).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" })}</span>
                <Motivo texto={e.detalle} />
              </li>
            ))}
          </ol>
          {(detalle.correcciones?.length ?? 0) > 0 && (
            <>
              <h3>Correcciones registradas</h3>
              <ul>{detalle.correcciones!.map((c, i) => <li key={i}>{etiquetaCampo(c.campo)}: {String(c.extraido ?? "—")} → {String(c.corregido)} <span className="muted">· {c.usuario}</span></li>)}</ul>
            </>
          )}
        </section>
      </div>
    </>
  );
}

/** Campos que un auditor corrige con frecuencia, por su nombre. La ruta técnica queda como último recurso. */
const CAMPOS_CORREGIBLES: { ruta: string; etiqueta: string }[] = [
  { ruta: "nivel_prioridad", etiqueta: "Prioridad" },
  { ruta: "clasificacion.tipo", etiqueta: "Tipo de documento" },
  { ruta: "extraccion.fecha_documento", etiqueta: "Fecha del documento" },
  { ruta: "extraccion.paciente.documento.tipo", etiqueta: "Tipo de documento del paciente" },
  { ruta: "extraccion.paciente.documento.valor", etiqueta: "Número de documento del paciente" },
  { ruta: "extraccion.paciente.edad", etiqueta: "Edad del paciente" },
  { ruta: "extraccion.diagnosticos[0].texto", etiqueta: "Diagnóstico principal" },
  { ruta: "extraccion.diagnosticos[0].cie10_sugerido", etiqueta: "Código CIE-10 del diagnóstico" },
  { ruta: "extraccion.profesional.registro_profesional", etiqueta: "Registro del profesional" },
  { ruta: "extraccion.medicamentos[0].dci", etiqueta: "Medicamento (DCI)" },
  { ruta: "extraccion.medicamentos[0].dosis", etiqueta: "Dosis del medicamento" },
  { ruta: "extraccion.medicamentos[0].frecuencia", etiqueta: "Frecuencia del medicamento" },
];
const OTRO = "__otro";

function etiquetaCampo(ruta: string): string {
  return CAMPOS_CORREGIBLES.find((c) => c.ruta === ruta)?.etiqueta ?? ruta;
}

function SelectorCampo({ correccion, onChange }: { correccion: Correccion; onChange: (c: Correccion) => void }) {
  const conocido = correccion.campo === "" || CAMPOS_CORREGIBLES.some((c) => c.ruta === correccion.campo);
  const [otro, setOtro] = useState(!conocido);
  return (
    <>
      <label>
        Campo a corregir
        <select value={otro ? OTRO : correccion.campo} onChange={(e) => {
          if (e.target.value === OTRO) { setOtro(true); onChange({ ...correccion, campo: "" }); }
          else { setOtro(false); onChange({ ...correccion, campo: e.target.value }); }
        }}>
          <option value="">Elige el campo…</option>
          {CAMPOS_CORREGIBLES.map((c) => <option key={c.ruta} value={c.ruta}>{c.etiqueta}</option>)}
          <option value={OTRO}>Otro campo (ruta técnica)…</option>
        </select>
      </label>
      {otro && (
        <label>
          Ruta técnica del campo
          <input value={correccion.campo} onChange={(e) => onChange({ ...correccion, campo: e.target.value })} placeholder="extraccion.signos_vitales.SpO2" />
        </label>
      )}
    </>
  );
}

/** Motivo de un evento: frase clínica visible y, plegado, el detalle técnico para soporte. */
function Motivo({ texto }: { texto: string }) {
  const { resumen, tecnico } = motivoLegible(texto);
  return (
    <div className="motivo">
      {resumen}
      {tecnico && (
        <details className="tecnico">
          <summary>Detalle técnico</summary>
          <code>{tecnico}</code>
        </details>
      )}
    </div>
  );
}
