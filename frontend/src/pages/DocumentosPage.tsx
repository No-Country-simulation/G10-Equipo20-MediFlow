import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { Link } from "react-router-dom";

import { enviarArchivo, enviarDocumento, ErrorApi, listarDocumentos } from "../api";
import { etiquetaMotivo, mensajeDeRechazo } from "../app/mensajes";
import { plazoDeRevision } from "../app/plazos";
import { CASOS } from "../data/casos";
import { ChipPlazo, TagEstado, TagPrioridad } from "../components/Tags";
import type { CanalOrigen, Cobertura, DocumentoDetalle, EstadoDocumento, Listado, NivelPrioridad } from "../types";

const CANALES: CanalOrigen[] = ["Guardia_Emergencias", "Consulta_Ambulatoria", "Hospitalizado", "Externo"];
const COBERTURAS: Cobertura[] = ["contributivo", "subsidiado", "especial_excepcion", "soat", "arl", "plan_voluntario", "no_afiliado"];
const ESTADOS: EstadoDocumento[] = ["RECIBIDO", "VALIDADO", "EN_REVISION_HUMANA", "ENRUTADO", "ENTREGADO", "RECHAZADO", "FALLO_TECNICO"];
const NIVELES: NivelPrioridad[] = ["Crítico", "Urgente", "Rutina"];
const LIMITE = 20;
const TAMANO_MAXIMO = 10 * 1024 * 1024;

function tiempoRelativo(iso: string | null): string {
  if (!iso) return "";
  const minutos = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutos < 1) return "ahora";
  if (minutos < 60) return `hace ${minutos} min`;
  if (minutos < 24 * 60) return `hace ${Math.round(minutos / 60)} h`;
  return new Date(iso).toLocaleDateString("es-CO");
}

export function DocumentosPage() {
  // --- carga -------------------------------------------------------------
  const [documentoId, setDocumentoId] = useState("");
  const [canal, setCanal] = useState<CanalOrigen>("Consulta_Ambulatoria");
  const [cobertura, setCobertura] = useState<Cobertura | "">("");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [modoTexto, setModoTexto] = useState(false);
  const [texto, setTexto] = useState("");
  const [arrastrando, setArrastrando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [errorCarga, setErrorCarga] = useState<string | null>(null);
  const [ultimo, setUltimo] = useState<DocumentoDetalle | null>(null);
  const inputArchivo = useRef<HTMLInputElement>(null);

  // --- tabla -------------------------------------------------------------
  const [busqueda, setBusqueda] = useState("");
  const [q, setQ] = useState("");
  const [estado, setEstado] = useState<EstadoDocumento | "">("");
  const [nivel, setNivel] = useState<NivelPrioridad | "">("");
  const [offset, setOffset] = useState(0);
  const [listado, setListado] = useState<Listado | null>(null);
  const [errorLista, setErrorLista] = useState<string | null>(null);

  const cargarLista = useCallback(() => {
    listarDocumentos({ q, estado: estado || undefined, nivel: nivel || undefined, limit: LIMITE, offset })
      .then((l) => { setListado(l); setErrorLista(null); })
      .catch((e) => setErrorLista(e instanceof ErrorApi ? e.detalle : "No hay conexión con la API."));
  }, [q, estado, nivel, offset]);

  useEffect(() => { cargarLista(); }, [cargarLista]);

  const listo = documentoId.trim() !== "" && (modoTexto ? texto.trim() !== "" : archivo !== null) && !enviando;

  function elegirArchivo(f: File | null) {
    setErrorCarga(null);
    if (f && f.size > TAMANO_MAXIMO) {
      setErrorCarga(mensajeDeRechazo("tamano_excedido"));
      return;
    }
    setArchivo(f);
    if (f && !documentoId.trim()) setDocumentoId(f.name.replace(/\.[^.]+$/, "").toUpperCase().replace(/[^A-Z0-9-]+/g, "-").slice(0, 40));
  }

  function alSoltar(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setArrastrando(false);
    elegirArchivo(e.dataTransfer.files?.[0] ?? null);
  }

  function cargarCaso(id: string) {
    const caso = CASOS.find((c) => c.id === id);
    if (!caso) return;
    setModoTexto(true);
    setArchivo(null);
    setDocumentoId(caso.documento_id);
    setCanal(caso.canal_origen);
    setCobertura(caso.cobertura_paciente ?? "");
    setTexto(caso.texto);
  }

  async function cargar() {
    setEnviando(true);
    setErrorCarga(null);
    setUltimo(null);
    try {
      const datos = { documento_id: documentoId.trim(), canal_origen: canal, cobertura_paciente: cobertura || null };
      const detalle = modoTexto
        ? await enviarDocumento({ ...datos, tipo_contenido: "texto", contenido_texto: texto })
        : await enviarArchivo(archivo!, datos);
      if (detalle.codigo_error) {
        setErrorCarga(mensajeDeRechazo(detalle.codigo_error));
      } else {
        setUltimo(detalle);
        setArchivo(null);
        setTexto("");
        setDocumentoId("");
      }
      setOffset(0);
      cargarLista();
    } catch (e) {
      setErrorCarga(e instanceof ErrorApi ? `${e.status}: ${e.detalle}` : "No hay conexión con la API.");
    } finally {
      setEnviando(false);
    }
  }

  const total = listado?.total ?? 0;
  const desde = total === 0 ? 0 : offset + 1;
  const hasta = Math.min(offset + LIMITE, total);

  return (
    <>
      <header className="encabezado">
        <div>
          <h1>Documentos</h1>
          <p className="sub">Carga, consulta y estado del procesamiento. Las listas no muestran datos del paciente (RN-K1).</p>
        </div>
        <div className="casos" aria-label="Casos sintéticos">
          {CASOS.map((c) => (
            <button key={c.id} type="button" className="secundario" title={c.descripcion} onClick={() => cargarCaso(c.id)}>{c.nombre}</button>
          ))}
        </div>
      </header>

      <section className="carga" aria-labelledby="titulo-carga">
        <div
          className={`dropzone ${arrastrando ? "activa" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setArrastrando(true); }}
          onDragLeave={() => setArrastrando(false)}
          onDrop={alSoltar}
        >
          {modoTexto ? (
            <label style={{ width: "100%", textAlign: "left" }}>
              Texto clínico
              <textarea rows={8} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Pega aquí el texto del documento" />
            </label>
          ) : (
            <>
              <span className="titulo" id="titulo-carga">Arrastra un PDF, PNG o JPG</span>
              <span className="muted">o elígelo desde tu equipo · hasta 10 MB · se valida el contenido, no la extensión (RN-A1)</span>
              <label className="secundario" style={{ alignItems: "center" }}>
                <span className="oculto-visual">Elegir archivo</span>
                <input ref={inputArchivo} type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                  onChange={(e) => elegirArchivo(e.target.files?.[0] ?? null)} />
                <button type="button" className="secundario" onClick={() => inputArchivo.current?.click()}>Elegir archivo</button>
              </label>
              {archivo && (
                <span className="adjunto">
                  <strong>{archivo.name}</strong>
                  <span className="muted">{Math.max(1, Math.round(archivo.size / 1024))} KB</span>
                  <button type="button" className="enlace" onClick={() => setArchivo(null)}>Quitar</button>
                </span>
              )}
            </>
          )}
          <button type="button" className="enlace" onClick={() => { setModoTexto((v) => !v); setArchivo(null); }}>
            {modoTexto ? "Prefiero adjuntar un archivo" : "Pegar texto en lugar de un archivo"}
          </button>
        </div>

        <div className="tarjeta">
          <h2>Datos del envío</h2>
          <div className="campos" style={{ marginTop: 8 }}>
            <label className="ancho">
              documento_id
              <input value={documentoId} onChange={(e) => setDocumentoId(e.target.value)} placeholder="DOC-CLIN-2026-8942" />
            </label>
            <label>
              Canal de origen
              <select value={canal} onChange={(e) => setCanal(e.target.value as CanalOrigen)}>
                {CANALES.map((c) => <option key={c} value={c}>{c.replace("_", " ")}</option>)}
              </select>
            </label>
            <label>
              Cobertura
              <select value={cobertura} onChange={(e) => setCobertura(e.target.value as Cobertura | "")}>
                <option value="">no informada</option>
                {COBERTURAS.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          </div>
          <div className="acciones" style={{ marginTop: 12 }}>
            <button type="button" disabled={!listo} onClick={cargar}>{enviando ? "Procesando…" : "Cargar documento"}</button>
          </div>
          {errorCarga && <div className="estado-carga error" role="alert">{errorCarga}</div>}
          {ultimo && (
            <div className="estado-carga" role="status" aria-label="Resultado de la carga">
              <code>{ultimo.documento_id}</code>
              <TagPrioridad nivel={ultimo.nivel_prioridad} />
              <TagEstado estado={ultimo.estado} />
              {ultimo.duplicado && <span className="muted">Ya se había procesado; se muestra el resultado previo (RN-O1).</span>}
              <Link to={`/documentos/${encodeURIComponent(ultimo.documento_id)}`}>Abrir ›</Link>
            </div>
          )}
        </div>
      </section>

      <section className="tarjeta" style={{ marginTop: 16, padding: 0 }}>
        <div style={{ padding: "12px 16px 0" }}>
          <h2>Historial <span className="muted" style={{ fontWeight: 400 }}>· {total} documento{total === 1 ? "" : "s"}</span></h2>
          <div className="filtros">
            <label>
              Buscar
              <input value={busqueda} onChange={(e) => setBusqueda(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { setOffset(0); setQ(busqueda.trim()); } }}
                placeholder="documento_id o nombre de archivo · Enter para buscar" />
            </label>
            <label>
              Estado
              <select value={estado} onChange={(e) => { setOffset(0); setEstado(e.target.value as EstadoDocumento | ""); }}>
                <option value="">Todos los estados</option>
                {ESTADOS.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
              </select>
            </label>
            <label>
              Prioridad
              <select value={nivel} onChange={(e) => { setOffset(0); setNivel(e.target.value as NivelPrioridad | ""); }}>
                <option value="">Todas</option>
                {NIVELES.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
          </div>
        </div>
        {errorLista && <p className="error" style={{ padding: "0 16px" }}>{errorLista}</p>}
        <div className="scroll">
          <table className="tabla-densa">
            <thead>
              <tr><th>Documento</th><th>Tipo</th><th>Prioridad</th><th>Estado</th><th>Plazo</th><th></th></tr>
            </thead>
            <tbody>
              {listado?.items.map((d) => (
                <tr key={`${d.documento_id}-${d.version}`} data-testid="fila-documento" className={`fila ${d.nivel_prioridad === "Crítico" ? "critico" : d.nivel_prioridad === "Urgente" ? "urgente" : d.nivel_prioridad === "Rutina" ? "rutina" : ""}`}>
                  <td>
                    <code>{d.documento_id}</code>
                    <span className="secundaria">
                      {d.nombre_archivo ?? "texto pegado"}{d.num_paginas && d.num_paginas > 1 ? ` · ${d.num_paginas} pág` : ""} · {tiempoRelativo(d.creado_en)}
                    </span>
                  </td>
                  <td>{d.tipo ?? <span className="muted">—</span>}{d.motivo_auditoria && <span className="secundaria">{etiquetaMotivo(d.motivo_auditoria)}</span>}</td>
                  <td><TagPrioridad nivel={d.nivel_prioridad} /></td>
                  <td><TagEstado estado={d.estado} /></td>
                  <td><ChipPlazo plazo={plazoDeRevision(d.estado, d.nivel_prioridad, d.creado_en)} /></td>
                  <td><Link to={`/documentos/${encodeURIComponent(d.documento_id)}`}>Abrir ›</Link></td>
                </tr>
              ))}
              {listado && listado.items.length === 0 && (
                <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 24 }}>No hay documentos con estos filtros.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="paginacion" style={{ padding: "10px 16px" }}>
          <span>Mostrando {desde}–{hasta} de {total}</span>
          <span className="acciones">
            <button type="button" className="secundario" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMITE))}>Anterior</button>
            <button type="button" className="secundario" disabled={hasta >= total} onClick={() => setOffset(offset + LIMITE)}>Siguiente</button>
          </span>
        </div>
      </section>
    </>
  );
}
