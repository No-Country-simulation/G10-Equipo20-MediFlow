import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { bandejaAutorizaciones, ErrorApi, resolverAutorizacion } from "../api";
import { useUsuario } from "../app/usuario";
import { TagPrioridad } from "../components/Tags";
import type { BandejaAutorizaciones, OrdenPorAutorizar } from "../types";

const MOTIVO_DESTINO: Record<string, string> = {
  solicitud_autorizacion_eps: "Solicitud de autorización a la EPS",
  documentacion_incompleta: "Documentación incompleta",
  via_rapida: "Vía rápida (Urgente)",
  informe_atencion_inicial_urgencias: "Informe de atención inicial de urgencias",
};

/** Auditoría de autorizaciones: órdenes ambulatorias por autorizar y avisos de urgencias que no esperan (RN-E5, RN-E9, RN-CO13). */
export function AutorizacionesPage() {
  const [bandeja, setBandeja] = useState<BandejaAutorizaciones | null>(null);
  const [pestana, setPestana] = useState<"por_autorizar" | "avisos">("por_autorizar");
  const [usuario] = useUsuario();
  const [motivos, setMotivos] = useState<Record<string, string>>({});
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = () => bandejaAutorizaciones().then(setBandeja).catch(() => setError("No hay conexión con la API."));
  useEffect(() => { cargar(); }, []);

  async function resolver(orden: OrdenPorAutorizar, accion: "aprobar" | "devolver") {
    setMensaje(null);
    try {
      const r = await resolverAutorizacion(orden.documento_id, { accion, usuario: usuario.trim(), motivo: (motivos[orden.documento_id] ?? "").trim() });
      setMensaje(`${orden.documento_id}: ${r.autorizacion.estado} por ${r.autorizacion.usuario} · estado ${r.estado}`);
      cargar();
    } catch (e) {
      setMensaje(e instanceof ErrorApi ? `${e.status}: ${e.detalle}` : "No hay conexión con la API.");
    }
  }

  const yo = usuario.trim();
  const porAutorizar = bandeja?.por_autorizar ?? [];
  const avisos = bandeja?.avisos_urgencias ?? [];

  return (
    <>
      <header className="encabezado">
        <div>
          <h1>Autorizaciones</h1>
          <p className="sub">Órdenes ambulatorias con su documentación mínima: justificación, diagnóstico codificado, CUPS y cobertura. Las de urgencias y hospitalización no esperan aquí: llegan como aviso.</p>
        </div>
      </header>
      <div className="pestanas" role="tablist">
        <button type="button" role="tab" aria-selected={pestana === "por_autorizar"} className={pestana === "por_autorizar" ? "" : "secundario"} onClick={() => setPestana("por_autorizar")}>Por autorizar ({porAutorizar.length})</button>
        <button type="button" role="tab" aria-selected={pestana === "avisos"} className={pestana === "avisos" ? "" : "secundario"} onClick={() => setPestana("avisos")}>Avisos de urgencias ({avisos.length})</button>
      </div>
      {mensaje && <p className="estado-carga" role="status">{mensaje}</p>}
      {error && <p className="error">{error}</p>}

      {pestana === "por_autorizar" && (
        <section className="tarjeta" style={{ padding: 0 }}>
          <div className="scroll">
            <table className="tabla-densa">
              <thead><tr><th>Orden</th><th>Procedimiento · CUPS</th><th>Cobertura</th><th>Documentación</th><th>Resolución</th></tr></thead>
              <tbody>
                {porAutorizar.map((o) => {
                  const motivo = motivos[o.documento_id] ?? "";
                  return (
                    <tr key={`${o.documento_id}-${o.version}`} data-testid="fila-orden" className={`fila ${o.nivel_prioridad === "Urgente" ? "urgente" : "rutina"}`}>
                      <td>
                        <Link to={`/documentos/${encodeURIComponent(o.documento_id)}`}><code>{o.documento_id}</code></Link>
                        <span className="secundaria">{o.fecha_documento ?? ""} · <TagPrioridad nivel={o.nivel_prioridad} /></span>
                      </td>
                      <td>{o.procedimientos.join(", ") || "—"}<span className="secundaria">CUPS {o.cups.length ? o.cups.join(", ") : "sin código"} · {o.diagnosticos.join("; ")}</span></td>
                      <td>{o.cobertura ?? <span className="muted">no informada</span>}<span className="secundaria">{MOTIVO_DESTINO[o.motivo_destino ?? ""] ?? o.motivo_destino ?? ""}</span></td>
                      <td>{o.documentacion_incompleta ? <span className="tag urgente">Documentación incompleta</span> : <span className="tag exito">Completa</span>}<span className="secundaria">{o.justificacion}</span></td>
                      <td>
                        <label>
                          <span className="oculto-visual">Motivo para {o.documento_id}</span>
                          <input value={motivo} placeholder="Motivo (obligatorio para devolver)" onChange={(e) => setMotivos({ ...motivos, [o.documento_id]: e.target.value })} />
                        </label>
                        <div className="acciones" style={{ marginTop: 6 }}>
                          <button type="button" disabled={!yo} onClick={() => resolver(o, "aprobar")}>Aprobar</button>
                          <button type="button" className="secundario" disabled={!yo || !motivo.trim()} onClick={() => resolver(o, "devolver")}>Devolver al solicitante</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {bandeja && porAutorizar.length === 0 && <tr><td colSpan={5} className="muted" style={{ textAlign: "center", padding: 24 }}>No hay órdenes por autorizar.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {pestana === "avisos" && (
        <section className="tarjeta" style={{ padding: 0 }}>
          <div className="scroll">
            <table className="tabla-densa">
              <thead><tr><th>Orden</th><th>Procedimiento · CUPS</th><th>Canal</th><th>Aviso</th></tr></thead>
              <tbody>
                {avisos.map((o) => (
                  <tr key={`${o.documento_id}-${o.version}`} data-testid="fila-aviso" className={`fila ${o.nivel_prioridad === "Crítico" ? "critico" : o.nivel_prioridad === "Urgente" ? "urgente" : "rutina"}`}>
                    <td><Link to={`/documentos/${encodeURIComponent(o.documento_id)}`}><code>{o.documento_id}</code></Link><span className="secundaria"><TagPrioridad nivel={o.nivel_prioridad} /></span></td>
                    <td>{o.procedimientos.join(", ")}<span className="secundaria">CUPS {o.cups.join(", ") || "sin código"}</span></td>
                    <td>{o.canal_origen.replace("_", " ")}</td>
                    <td><span className="tag marca">Atención sin autorización previa</span><span className="secundaria">{MOTIVO_DESTINO[o.motivo_destino ?? ""] ?? ""} · solo informa a la EPS</span></td>
                  </tr>
                ))}
                {bandeja && avisos.length === 0 && <tr><td colSpan={4} className="muted" style={{ textAlign: "center", padding: 24 }}>Sin avisos de urgencias.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
