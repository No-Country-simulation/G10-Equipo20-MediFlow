import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { confirmarEntrega, consultarDocumento, ErrorApi, listarDocumentos } from "../api";
import { TagPrioridad } from "../components/Tags";
import type { DocumentoDetalle } from "../types";

interface FilaEntrega {
  detalle: DocumentoDetalle;
  entregas: Record<string, boolean>;
  pendientes: string[] | null;
}

/** Entregas: confirmar destinos de lo enrutado. Enrutado es la decisión; Entregado, el hecho (sección 3.3, RN-J7). */
export function EntregasPage() {
  const [filas, setFilas] = useState<FilaEntrega[] | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);

  useEffect(() => {
    let activo = true;
    listarDocumentos({ estado: "ENRUTADO", limit: 100 })
      .then((l) => Promise.all(l.items.map((i) => consultarDocumento(i.documento_id))))
      .then((detalles) => activo && setFilas(detalles.map((d) => ({ detalle: d, entregas: d.entregas ?? {}, pendientes: null }))))
      .catch(() => activo && setFilas([]));
    return () => { activo = false; };
  }, []);

  async function confirmar(fila: FilaEntrega, destino: string) {
    setMensaje(null);
    try {
      const r = await confirmarEntrega(fila.detalle.documento_id, destino);
      setFilas((actuales) => (actuales ?? []).map((f) => (f.detalle.documento_id === fila.detalle.documento_id ? { ...f, entregas: r.entregas, pendientes: r.pendientes, detalle: { ...f.detalle, estado: r.estado } } : f)));
      if (r.estado === "ENTREGADO") setMensaje(`${fila.detalle.documento_id} entregado. Estado final (RN-I1).`);
    } catch (e) {
      setMensaje(e instanceof ErrorApi ? `${e.status}: ${e.detalle}` : "No hay conexión con la API.");
    }
  }

  return (
    <>
      <header className="encabezado">
        <div>
          <h1>Entregas</h1>
          <p className="sub">Documentos enrutados a la espera de que los destinos confirmen. Un Crítico no se cierra sin acuse de su alerta (RN-J7); una entrega retenida a HCE espera la conciliación de identidad (RN-A4).</p>
        </div>
      </header>
      {mensaje && <p className="estado-carga" role="status">{mensaje}</p>}
      <section className="tarjeta" style={{ padding: 0 }}>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Documento</th><th>Destinos</th><th>Pendiente</th></tr></thead>
            <tbody>
              {filas?.map((f) => {
                const en = f.detalle.resultado?.enrutamiento;
                const plan = en ? [en.destino_principal, ...en.destinos_secundarios] : [];
                const retenidas = en?.entregas_retenidas ?? {};
                return (
                  <tr key={f.detalle.documento_id} data-testid="fila-entrega" className={`fila ${f.detalle.nivel_prioridad === "Crítico" ? "critico" : f.detalle.nivel_prioridad === "Urgente" ? "urgente" : "rutina"}`}>
                    <td><Link to={`/documentos/${encodeURIComponent(f.detalle.documento_id)}`}><code>{f.detalle.documento_id}</code></Link><span className="secundaria"><TagPrioridad nivel={f.detalle.nivel_prioridad} /> · {f.detalle.estado}</span></td>
                    <td>
                      <ul className="destinos" style={{ margin: 0 }}>
                        {plan.map((destino) => (
                          <li key={destino} style={{ borderBottom: "none", padding: "2px 0" }}>
                            <strong>{destino}</strong>
                            {retenidas[destino] ? <span className="aviso">retenida: {retenidas[destino]}</span>
                              : f.entregas[destino] ? <span className="ok">confirmada</span>
                              : f.detalle.estado === "ENRUTADO" && <button type="button" className="secundario" onClick={() => confirmar(f, destino)}>Confirmar {destino}</button>}
                          </li>
                        ))}
                      </ul>
                    </td>
                    <td>{f.pendientes ? (f.pendientes.length ? f.pendientes.join(", ") : <span className="ok">nada</span>) : <span className="muted">—</span>}</td>
                  </tr>
                );
              })}
              {filas && filas.length === 0 && <tr><td colSpan={3} className="muted" style={{ textAlign: "center", padding: 24 }}>No hay documentos enrutados pendientes de entrega.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
