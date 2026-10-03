import { ArrowLeft, ArrowRight, Check, CircleCheckBig, Keyboard, Maximize2, Minimize2, PanelLeftOpen, Pencil, ShieldCheck, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { colaRevision, confirmarEntrega, consultarDocumento, resolverRevision, urlOriginal, urlVistaPrevia } from "../api";
import { etiquetaConcepto, etiquetaDestino, etiquetaEstado, etiquetaMotivo, etiquetaTipo, motivoLegible, tituloHallazgos } from "../app/mensajes";
import { usePared } from "../app/pared";
import { calcularPlazo, PLAZO_ACUSE_MIN } from "../app/plazos";
import { useRol } from "../app/RolContext";
import { rolPuedeVer } from "../app/roles";
import { enmascarar, useUsuario } from "../app/usuario";
import { AccionAcuse } from "../components/AccionAcuse";
import { EstadoMensaje, textoDeError, type Mensaje } from "../components/EstadoMensaje";
import { HistorialDecisiones } from "../components/HistorialDecisiones";
import { TagEstado, TagPrioridad } from "../components/Tags";
import { Transcripcion } from "../components/Transcripcion";
import type { AccionRevision, DocumentoDetalle, ItemCola } from "../types";

type ClaveConfianza = "identidad_paciente" | "medicamento_dosis" | "diagnostico_codigo" | "profesional";
type Decision = "aprobar" | "rechazar";

interface Correccion {
  campo: string;
  valor: string;
}

const CLAVE_ATAJOS = "mediflow.atajos";

function leerAtajos(): boolean {
  try {
    return localStorage.getItem(CLAVE_ATAJOS) !== "no";
  } catch {
    return true;
  }
}

/** Un atajo de una tecla solo actúa si el foco no está en algo que ya usa esa tecla (WCAG 2.1.4). */
function esInteractivo(objetivo: EventTarget | null): boolean {
  if (!(objetivo instanceof HTMLElement)) return false;
  return objetivo.isContentEditable || ["INPUT", "TEXTAREA", "SELECT", "BUTTON", "A", "SUMMARY"].includes(objetivo.tagName);
}

function PildoraConfianza({ valor, umbral }: { valor: number | null | undefined; umbral: number | undefined }) {
  if (valor === null || valor === undefined) return <span className="tag neutro">sin dato</span>;
  const bajo = umbral !== undefined && valor < umbral;
  return <span className={`tag ${bajo ? "urgente" : "exito"}`} title="Confianza de la lectura automática frente al umbral del campo">{valor.toFixed(2)}</span>;
}

const PASADO: Record<AccionRevision, string> = { aprobar: "Aprobado", corregir: "Corregido y reevaluado", rechazar: "Rechazado", transcribir: "Transcrito y evaluado" };

export function DetalleDocumentoPage() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const desdeCola = params.get("cola") === "1";
  const navigate = useNavigate();
  const { rol, modoDiscreto, alternarModoDiscreto } = useRol();
  const [usuario] = useUsuario();
  const { activo: pared, alternar: alternarPared } = usePared();

  const [detalle, setDetalle] = useState<DocumentoDetalle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pagina, setPagina] = useState(1);
  const [ampliada, setAmpliada] = useState(false);
  const [textoOriginal, setTextoOriginal] = useState<string | null>(null);
  const [cola, setCola] = useState<ItemCola[]>([]);
  const [motivo, setMotivo] = useState("");
  const [correccion, setCorreccion] = useState<Correccion | null>(null);
  const [confirmacion, setConfirmacion] = useState<Decision | null>(null);
  const [cierre, setCierre] = useState<{ accion: AccionRevision; estado: string; prioridad?: string; alerta?: boolean } | null>(null);
  const [mensaje, setMensaje] = useState<Mensaje | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [atajos, setAtajos] = useState(leerAtajos);
  const [transcripcionSucia, setTranscripcionSucia] = useState(false);
  const [entregas, setEntregas] = useState<Record<string, boolean>>({});
  const [pendientes, setPendientes] = useState<string[] | null>(null);
  const [ahora, setAhora] = useState(() => new Date());
  const botonConfirmar = useRef<HTMLButtonElement>(null);
  const botonSiguiente = useRef<HTMLButtonElement>(null);
  const tituloCierre = useRef<HTMLParagraphElement>(null);

  const cargar = useCallback(() => {
    consultarDocumento(id)
      .then((d) => { setDetalle(d); setEntregas(d.entregas ?? {}); setError(null); })
      .catch((e) => setError(textoDeError(e)));
  }, [id]);

  useEffect(() => {
    // Al cambiar de documento no queda nada del anterior en pantalla mientras carga el siguiente.
    setDetalle(null); setTranscripcionSucia(false);
    setPagina(1); setCorreccion(null); setMensaje(null); setPendientes(null); setConfirmacion(null); setCierre(null); setMotivo("");
    cargar();
  }, [cargar]);
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
  // El foco va a donde está la siguiente acción: confirmar, o seguir con el próximo caso.
  useEffect(() => { if (confirmacion) botonConfirmar.current?.focus(); }, [confirmacion]);
  useEffect(() => { if (cierre) (botonSiguiente.current ?? tituloCierre.current)?.focus(); }, [cierre]);

  const r = detalle?.resultado ?? null;
  const enRevision = detalle?.estado === "EN_REVISION_HUMANA";
  const transcribiendo = enRevision && r?.evaluacion.motivo_auditoria === "fallo_tecnico";
  const posicionCola = useMemo(() => cola.findIndex((c) => c.documento_id === id), [cola, id]);
  const siguiente = posicionCola >= 0 ? cola[posicionCola + 1] : undefined;
  const firma = usuario.trim();

  const irA = useCallback((desplazamiento: number) => {
    if (posicionCola < 0) return;
    const destino = cola[posicionCola + desplazamiento];
    if (destino) navigate(`/documentos/${encodeURIComponent(destino.documento_id)}?cola=1`);
  }, [cola, posicionCola, navigate]);

  const resolver = useCallback(async (accion: AccionRevision, extra: { correcciones?: Record<string, unknown>; transcripcion?: Record<string, unknown> } = {}) => {
    if (!detalle || !firma || enviando) return;
    if (accion === "rechazar" && !motivo.trim()) return;
    setEnviando(true);
    setMensaje(null);
    setConfirmacion(null);
    try {
      const resp = await resolverRevision(detalle.documento_id, {
        accion, motivo: motivo || (accion === "transcribir" ? "transcrito desde el original" : ""),
        correcciones: extra.correcciones ?? null, transcripcion: extra.transcripcion ?? null,
      });
      setCorreccion(null);
      setMotivo("");
      if (accion === "corregir") setMensaje({ texto: `${PASADO[accion]}. Queda en ${etiquetaEstado(resp.estado)}.` });
      else setCierre({ accion, estado: resp.estado, prioridad: resp.resultado?.clasificacion.nivel_prioridad, alerta: !!resp.resultado?.notificacion_generada });
      cargar();
    } catch (e) {
      setMensaje({ texto: textoDeError(e), error: true });
    } finally {
      setEnviando(false);
    }
  }, [detalle, firma, enviando, motivo, rol.id, cargar]);

  const pedir = useCallback((decision: Decision) => {
    if (!enRevision || enviando) return;
    // Un atajo que no puede actuar lo dice, en vez de no hacer nada.
    if (transcribiendo && decision === "aprobar") { setMensaje({ texto: "Este documento no tiene lectura que aprobar: completa la transcripción.", error: true }); return; }
    if (decision === "rechazar" && !motivo.trim()) { setMensaje({ texto: "Rechazar exige escribir el motivo.", error: true }); return; }
    setConfirmacion(decision);
  }, [enRevision, transcribiendo, firma, enviando, motivo]);

  // Atajos del banco de trabajo: A y R abren la confirmación, C abre la corrección, J y K recorren la cola.
  useEffect(() => {
    function alTeclear(e: KeyboardEvent) {
      if (e.key === "Escape") { setConfirmacion(null); return; }
      // En la pared no hay banco de trabajo: una tecla suelta de quien pasa no decide nada.
      if (pared || !atajos || e.altKey || e.ctrlKey || e.metaKey || esInteractivo(e.target)) return;
      const tecla = e.key.toLowerCase();
      if ((tecla === "j" || tecla === "k") && transcripcionSucia) {
        setMensaje({ texto: "Tienes una transcripción sin guardar. Guárdala o descártala antes de pasar a otro documento.", error: true });
        return;
      }
      if (tecla === "j") irA(1);
      else if (tecla === "k") irA(-1);
      else if (tecla === "a") pedir("aprobar");
      else if (tecla === "r") pedir("rechazar");
      else if (tecla === "c" && enRevision && !transcribiendo) setCorreccion((c) => c ?? { campo: "", valor: "" });
    }
    window.addEventListener("keydown", alTeclear);
    return () => window.removeEventListener("keydown", alTeclear);
  }, [irA, pedir, enRevision, transcribiendo, atajos, transcripcionSucia, pared]);

  function cambiarAtajos(activos: boolean) {
    setAtajos(activos);
    try { localStorage.setItem(CLAVE_ATAJOS, activos ? "si" : "no"); } catch { /* preferencia de esta sesión */ }
  }

  async function entregar(destino: string) {
    if (!detalle) return;
    try {
      const resp = await confirmarEntrega(detalle.documento_id, destino);
      setEntregas(resp.entregas);
      setPendientes(resp.pendientes);
      if (resp.estado !== detalle.estado) cargar();
    } catch (e) {
      setMensaje({ texto: textoDeError(e), error: true });
    }
  }

  if (error) return <p className="estado-carga error" role="alert" style={{ marginTop: 16 }}>{error}</p>;
  if (!detalle) return <p className="muted" style={{ marginTop: 16 }}>Cargando…</p>;

  const ver = (valor: string | null | undefined) => (modoDiscreto ? enmascarar(valor) : valor ?? "—");
  const conf = detalle.confianzas ?? {};
  const umb = detalle.umbrales ?? {};
  const bajo = (clave: ClaveConfianza) => conf[clave] !== null && conf[clave] !== undefined && umb[clave] !== undefined && (conf[clave] as number) < (umb[clave] as number);
  const alerta = detalle.alerta;
  const plazoAlerta = alerta ? calcularPlazo(alerta.emitida_en, PLAZO_ACUSE_MIN, ahora) : null;
  const plan = r ? (enRevision ? r.enrutamiento.destinos_tras_revision : [r.enrutamiento.destino_principal, ...r.enrutamiento.destinos_secundarios]) : [];
  const retenidas = r?.enrutamiento.entregas_retenidas ?? {};
  const docPaciente = r?.extraccion.paciente.documento;
  const titulo = tituloHallazgos(r?.extraccion.hallazgos_criticos_detectados);
  const eventos = [
    ...(detalle.transiciones ?? []).map((t) => ({ fecha: t.fecha_hora, texto: `${etiquetaEstado(t.a_estado)} · ${t.actor}`, detalle: t.motivo, tipo: "estado" as const })),
    ...(alerta ? [{ fecha: alerta.emitida_en, texto: "Alerta crítica emitida", detalle: `${alerta.canal} → ${alerta.destinatario}`, tipo: "alerta" as const }] : []),
    ...(alerta?.acusado_por ? [{ fecha: alerta.emitida_en, texto: `Acuse de ${alerta.acusado_por}`, detalle: "circuito cerrado", tipo: "acuse" as const }] : []),
  ].sort((a, b) => a.fecha.localeCompare(b.fecha));

  return (
    <>
      <header className="encabezado banco-cabecera">
        <div>
          {pared ? (
            <p className="volver-pared"><Link to="/alertas"><ArrowLeft size={20} aria-hidden="true" />Volver a Alertas</Link></p>
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              <Link to={desdeCola ? "/revision" : "/documentos"}>{desdeCola ? "Cola de revisión" : "Documentos"}</Link> / <code>{detalle.documento_id}</code>
              {desdeCola && posicionCola >= 0 && <> · {posicionCola + 1} de {cola.length} en la cola</>}
            </p>
          )}
          <div className="titulo-doc">
            <h1 className={titulo ? "hallazgo" : "id"}>{titulo || detalle.documento_id}</h1>
            <TagPrioridad nivel={detalle.nivel_prioridad} />
            <TagEstado estado={detalle.estado} />
          </div>
          <p className="sub">
            {titulo && <span className="id-doc"><code>{detalle.documento_id}</code> · </span>}
            {etiquetaTipo(r?.clasificacion.tipo) || "Sin clasificar"} · {detalle.canal_origen?.replace(/_/g, " ")} · versión {detalle.version}
            {detalle.nombre_archivo && <> · {modoDiscreto ? <span className="muted">nombre de archivo oculto</span> : <span className="archivo">{detalle.nombre_archivo}</span>}</>}
          </p>
        </div>
        {alerta && plazoAlerta && (
          <div className={`alerta-doc ${alerta.estado_acuse === "acusado" ? "acusada" : plazoAlerta.vencido ? "escalada" : ""}`} data-testid="alerta-documento">
            <strong>{alerta.estado_acuse === "acusado" ? `Alerta acusada por ${alerta.acusado_por}` : plazoAlerta.vencido ? "Alerta crítica escalada" : "Alerta crítica sin acuse"}</strong>
            <span className="muted">{alerta.canal} → {alerta.destinatario}{alerta.estado_acuse !== "acusado" && <> · <span className={`plazo ${plazoAlerta.vencido ? "vencido" : plazoAlerta.apremia ? "apremia" : ""}`}>{plazoAlerta.texto}</span></>}</span>
            {alerta.estado_acuse !== "acusado" && <AccionAcuse documentoId={detalle.documento_id} contexto={`${titulo || "alerta crítica"}, ${detalle.documento_id}`} onAcusado={(resp) => { setMensaje({ texto: `Acuse registrado por ${resp.acusado_por}. Circuito cerrado.` }); cargar(); }} />}
          </div>
        )}
      </header>

      <EstadoMensaje mensaje={mensaje} />

      {pared ? (
        <section className="tarjeta resguardo-pared" data-testid="documento-resguardado" aria-labelledby="resguardo-titulo">
          <ShieldCheck size={28} aria-hidden="true" />
          <div>
            <h2 id="resguardo-titulo">El documento completo no se muestra en la pantalla compartida</h2>
            <p>El original, los datos extraídos y la decisión se revisan fuera de la vista de pared, para que el documento del paciente no quede a la vista de quien pasa.</p>
            <button type="button" className="secundario" onClick={alternarPared}><PanelLeftOpen size={18} aria-hidden="true" />Salir de la vista de pared para revisarlo</button>
          </div>
        </section>
      ) : (
      <div className={`banco ${transcribiendo ? "transcripcion-activa" : ""}`}>
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
                <button type="button" className="secundario" aria-label="Página anterior" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>‹</button>
                <span>pág {pagina} / {detalle.num_paginas ?? 1}</span>
                <button type="button" className="secundario" aria-label="Página siguiente" disabled={pagina >= (detalle.num_paginas ?? 1)} onClick={() => setPagina(pagina + 1)}>›</button>
                <button type="button" className="secundario" onClick={() => setAmpliada((v) => !v)} aria-pressed={ampliada}>
                  {ampliada ? <Minimize2 size={16} aria-hidden="true" /> : <Maximize2 size={16} aria-hidden="true" />}{ampliada ? "Reducir" : "Ampliar"}
                </button>
              </div>
              <img className={`vista-previa ${modoDiscreto ? "discreto" : ""} ${ampliada ? "ampliada" : ""}`} src={urlVistaPrevia(detalle.documento_id, pagina)} alt={`Página ${pagina} del original`} />
            </>
          )}
          {(detalle.formato === "png" || detalle.formato === "jpeg") && (
            <img className={`vista-previa ${modoDiscreto ? "discreto" : ""} ${ampliada ? "ampliada" : ""}`} src={urlOriginal(detalle.documento_id)} alt="Imagen original" />
          )}
          {detalle.formato === "txt" && (
            <pre className="texto-original">{textoOriginal === null ? "Original no disponible." : modoDiscreto ? (detalle.texto_enviado_llm ?? "") : textoOriginal}</pre>
          )}
          {modoDiscreto && detalle.formato !== "txt" && <p className="muted">Vista previa difuminada: datos del paciente ocultos en esta pantalla.</p>}
          <p><a href={urlOriginal(detalle.documento_id)} target="_blank" rel="noreferrer">Abrir el original en otra pestaña</a></p>
          <details>
            <summary>Qué salió al LLM (texto seudonimizado)</summary>
            <pre className="texto-original">{detalle.texto_enviado_llm || "Sin texto: el documento se leyó como imagen."}</pre>
          </details>
        </section>

        {/* ------------------------------------------------ Extracción o transcripción */}
        <section className="panel" aria-labelledby="p-extraccion">
          <div className="panel-cabecera">
            <h2 id="p-extraccion">{transcribiendo ? "Transcripción" : "Extracción"}</h2>
            <span className="muted">{transcribiendo ? "desde el original" : "confianza por campo"}</span>
          </div>
          {transcribiendo ? (
            <Transcripcion key={`${detalle.documento_id}-${detalle.version}`} habilitado={!!firma} enviando={enviando} onCambio={setTranscripcionSucia}
              prioridadActual={detalle.nivel_prioridad} discreto={modoDiscreto}
              onEnviar={(t) => void resolver("transcribir", { transcripcion: t })} />
          ) : !r ? <p className="muted">Sin resultado.</p> : (
            <>
              <dl className="campos-extraccion">
                <div data-testid="campo-identidad_paciente" className={bajo("identidad_paciente") ? "dudoso" : ""}>
                  <dt>Paciente</dt>
                  <dd><span>{ver(r.extraccion.paciente.nombre)}</span><span>· {r.extraccion.paciente.edad != null ? `${r.extraccion.paciente.edad} años` : "edad sin dato"}</span> <PildoraConfianza valor={conf.identidad_paciente} umbral={umb.identidad_paciente} /></dd>
                  <dd className="muted">Documento: {docPaciente?.tipo || docPaciente?.valor ? <>{docPaciente.tipo} {docPaciente.valor ? ver(docPaciente.valor) : ""}{docPaciente.estado && docPaciente.estado !== "verificado" && <> · {docPaciente.estado.replace(/_/g, " ")}</>}</> : "sin dato"}</dd>
                  {detalle.paciente_id != null && rolPuedeVer(rol, "/pacientes") && <dd><Link to={`/pacientes/${detalle.paciente_id}`}>Ficha del paciente ›</Link></dd>}
                  {bajo("identidad_paciente") && <dd className="aviso">Bajo el umbral {umb.identidad_paciente?.toFixed(2)} <button type="button" className="enlace" onClick={() => setCorreccion({ campo: "extraccion.paciente.documento.valor", valor: r.extraccion.paciente.documento.valor ?? "" })}>Corregir</button></dd>}
                </div>
                <div data-testid="campo-diagnostico_codigo" className={bajo("diagnostico_codigo") ? "dudoso" : ""}>
                  <dt>Diagnósticos</dt>
                  {r.extraccion.diagnosticos.map((d, i) => (
                    <dd key={i}>{d.texto} <code>{d.cie10_sugerido ?? "sin código"}</code> {d.cie11_sugerido && <code>{d.cie11_sugerido}</code>} {i === 0 && <PildoraConfianza valor={conf.diagnostico_codigo} umbral={umb.diagnostico_codigo} />}</dd>
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
                  <dd>{r.extraccion.fecha_documento ?? <span className="muted">sin dato</span>}</dd>
                </div>
                <div>
                  <dt>Signos vitales</dt>
                  <dd>FR {r.extraccion.signos_vitales.FR ?? "sd"} · SpO2 {r.extraccion.signos_vitales.SpO2 ?? "sd"} · FC {r.extraccion.signos_vitales.FC ?? "sd"} · PAS {r.extraccion.signos_vitales.PAS ?? "sd"} · T {r.extraccion.signos_vitales.Temp ?? "sd"}</dd>
                  <dd><strong>NEWS2 total: {r.extraccion.signos_vitales.NEWS2_total ?? "no aplica"}</strong> <span className="muted">calculado por el sistema · sd = sin dato</span></dd>
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

          {cierre && (
            <div className="cierre-caso" data-testid="cierre-caso">
              <p ref={tituloCierre} tabIndex={-1}><CircleCheckBig size={18} aria-hidden="true" /><strong>Caso cerrado: {PASADO[cierre.accion].toLowerCase()}.</strong> Queda en {etiquetaEstado(cierre.estado)}.
                {cierre.prioridad && cierre.accion === "transcribir" && <> Prioridad resultante: <strong>{cierre.prioridad}</strong>{cierre.alerta ? ", con alerta crítica activa." : ", sin alerta."}</>}</p>
              <div className="acciones">
                {desdeCola && siguiente && <button type="button" ref={botonSiguiente} onClick={() => irA(1)}>Siguiente caso <ArrowRight size={16} aria-hidden="true" /><kbd>J</kbd></button>}
                <Link to={desdeCola ? "/revision" : "/documentos"}>{desdeCola ? "Volver a la cola" : "Volver a Documentos"}</Link>
              </div>
            </div>
          )}

          <p className="muted firma" id="firma-decision">Firmas como <strong>{firma}</strong> · {rol.nombre}</p>

          {enRevision && r && (
            <>
              <p className="aviso">Requiere revisión: <strong>{etiquetaMotivo(r.evaluacion.motivo_auditoria)}</strong>{r.evaluacion.campos_dudosos.length > 0 && <> · dudosos: {r.evaluacion.campos_dudosos.join(", ")}</>}</p>
              {transcribiendo
                ? <p className="muted">La acción principal es completar la transcripción en el panel central. Si el documento no corresponde, recházalo con su motivo.</p>
                : <p><span className="muted">Plan tras revisión:</span> {plan.map(etiquetaDestino).join(" + ") || "sin plan"}</p>}
              <label>
                <span id="etiqueta-motivo">{transcribiendo ? "Motivo (obligatorio para rechazar)" : "Motivo (obligatorio para rechazar o bajar la prioridad)"}</span>
                <input value={motivo} onChange={(e) => setMotivo(e.target.value)} aria-labelledby="etiqueta-motivo" />
              </label>
              {correccion && !transcribiendo && (
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
                    <button type="button" disabled={!firma || !correccion.campo.trim()} onClick={() => resolver("corregir", { correcciones: { [correccion.campo.trim()]: correccion.valor } })}>Aplicar corrección</button>
                    <button type="button" className="secundario" onClick={() => setCorreccion(null)}>Cancelar</button>
                  </div>
                  <p className="muted">Las reglas se vuelven a aplicar sin llamar otra vez al LLM, y queda registrado el valor leído y el corregido.</p>
                </div>
              )}

              {confirmacion && (
                <div className={`confirmacion ${confirmacion}`} data-testid="confirmacion" role="group" aria-labelledby="confirmacion-titulo">
                  <p id="confirmacion-titulo">
                    {confirmacion === "aprobar"
                      ? <>¿Aprobar <strong>{detalle.documento_id}</strong>? Se enruta a <strong>{plan.map(etiquetaDestino).join(" + ") || "sin destino"}</strong>{plan.length > 0 && <span className="oculto-visual"> ({plan.join(", ")})</span>}.</>
                      : <>¿Rechazar <strong>{detalle.documento_id}</strong>? No se enruta a ningún destino. Motivo: «{motivo.trim()}».</>}
                  </p>
                  <div className="acciones">
                    <button type="button" ref={botonConfirmar} className={confirmacion === "rechazar" ? "peligro" : ""} disabled={enviando} onClick={() => resolver(confirmacion)}>
                      {confirmacion === "aprobar" ? <><Check size={16} aria-hidden="true" />Confirmar aprobación</> : <><X size={16} aria-hidden="true" />Confirmar rechazo</>}
                    </button>
                    <button type="button" className="secundario" onClick={() => setConfirmacion(null)}>Cancelar <kbd>Esc</kbd></button>
                  </div>
                </div>
              )}

              {!confirmacion && (
                <div className="acciones" style={{ marginTop: 8 }}>
                  {!transcribiendo && <button type="button" aria-describedby="firma-decision" disabled={!firma || enviando} onClick={() => pedir("aprobar")}><Check size={16} aria-hidden="true" />Aprobar <kbd>A</kbd></button>}
                  {!transcribiendo && <button type="button" className="secundario" disabled={!firma || enviando} onClick={() => setCorreccion((c) => c ?? { campo: "", valor: "" })}><Pencil size={16} aria-hidden="true" />Corregir <kbd>C</kbd></button>}
                  <button type="button" className="peligro" aria-describedby="firma-decision ayuda-rechazar" disabled={!firma || !motivo.trim() || enviando} onClick={() => pedir("rechazar")}><X size={16} aria-hidden="true" />Rechazar <kbd>R</kbd></button>
                  <span id="ayuda-rechazar" className={motivo.trim() ? "oculto-visual" : "muted pista"}>Rechazar exige escribir el motivo.</span>
                </div>
              )}

              <details className="ayuda-atajos">
                <summary><Keyboard size={16} aria-hidden="true" />Atajos de teclado</summary>
                <ul>
                  <li><kbd>A</kbd> aprobar y <kbd>R</kbd> rechazar: abren la confirmación; <kbd>Enter</kbd> confirma y <kbd>Esc</kbd> cancela.</li>
                  <li><kbd>C</kbd> abre la corrección. <kbd>J</kbd> y <kbd>K</kbd> pasan al caso siguiente y al anterior de la cola.</li>
                  <li>No actúan mientras escribes ni con el foco en un botón o un enlace.</li>
                </ul>
                <label className="interruptor"><input type="checkbox" checked={atajos} onChange={(e) => cambiarAtajos(e.target.checked)} />Usar atajos de una tecla</label>
              </details>
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
            {eventos.map((e, i) => {
              const repetido = i > 0 && motivoLegible(eventos[i - 1].detalle).resumen === motivoLegible(e.detalle).resumen && !motivoLegible(e.detalle).tecnico;
              return (
                <li key={i} data-testid="evento" className={e.tipo}>
                  <span className="estado">{e.texto}</span>
                  <span className="muted"> · {new Date(e.fecha).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" })}</span>
                  {!repetido && <Motivo texto={e.detalle} />}
                </li>
              );
            })}
          </ol>
          {(detalle.correcciones?.length ?? 0) > 0 && (
            <>
              <h3>Correcciones registradas</h3>
              <ul>{detalle.correcciones!.map((c, i) => <li key={i}>{etiquetaCampo(c.campo)}: {typeof c.extraido === "object" && c.extraido !== null ? "…" : String(c.extraido ?? "sin dato")} → {typeof c.corregido === "object" && c.corregido !== null ? "…" : String(c.corregido)} <span className="muted">· {c.usuario}</span></li>)}</ul>
            </>
          )}
        </section>
      </div>
      )}
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
