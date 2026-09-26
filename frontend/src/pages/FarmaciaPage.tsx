import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { colaFarmacia, ErrorApi, verificarReceta } from "../api";
import { useUsuario } from "../app/usuario";
import { TagPrioridad } from "../components/Tags";
import type { RecetaPorVerificar } from "../types";

/** Farmacia: recetas por verificar. Alto riesgo y control especial exigen dos personas distintas (RN-E6, RN-J6, RN-CO9). */
export function FarmaciaPage() {
  const [recetas, setRecetas] = useState<RecetaPorVerificar[] | null>(null);
  const [usuario, setUsuario] = useUsuario();
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = () => colaFarmacia().then(setRecetas).catch(() => setError("No hay conexión con la API."));
  useEffect(() => { cargar(); }, []);

  async function verificar(documentoId: string) {
    setMensaje(null);
    try {
      const r = await verificarReceta(documentoId, usuario.trim());
      setMensaje(r.completa ? `${documentoId} verificada (${r.verificaciones.length} de ${r.requeridas}) · estado ${r.estado}` : `${documentoId}: primera verificación registrada; falta la segunda por otra persona`);
      cargar();
    } catch (e) {
      setMensaje(e instanceof ErrorApi ? `${e.status}: ${e.detalle}` : "No hay conexión con la API.");
    }
  }

  const yo = usuario.trim();

  return (
    <>
      <header className="encabezado">
        <div>
          <h1>Farmacia</h1>
          <p className="sub">Recetas enrutadas a Farmacia. Alto riesgo y control especial piden doble verificación por dos personas distintas (RN-E6, RN-J6).</p>
        </div>
        <label style={{ minWidth: 260 }}>
          Usuario que verifica
          <input value={usuario} onChange={(e) => setUsuario(e.target.value)} placeholder="qf.maria" />
        </label>
      </header>
      {mensaje && <p className="estado-carga" role="status">{mensaje}</p>}
      {error && <p className="error">{error}</p>}
      <section className="tarjeta" style={{ padding: 0 }}>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Receta</th><th>Medicamentos (DCI)</th><th>Riesgo</th><th>Verificaciones</th><th></th></tr></thead>
            <tbody>
              {recetas?.map((r) => {
                const hechas = r.verificaciones.length;
                const yaFirme = r.verificaciones.some((v) => v.usuario === yo);
                const siguiente = hechas === 0 ? "Primera verificación" : "Segunda verificación";
                return (
                  <tr key={`${r.documento_id}-${r.version}`} data-testid="fila-receta" className={`fila ${r.alto_riesgo || r.control_especial ? "critico" : "rutina"}`}>
                    <td>
                      <Link to={`/documentos/${encodeURIComponent(r.documento_id)}`}><code>{r.documento_id}</code></Link>
                      <span className="secundaria">{r.fecha_documento ?? ""} · <TagPrioridad nivel={r.nivel_prioridad} /></span>
                    </td>
                    <td>
                      <ul style={{ margin: 0, paddingLeft: 16 }}>
                        {r.medicamentos.map((m, i) => (
                          <li key={i}>{m.dci} {m.dosis ?? ""}{m.dosis_valor && <span className="muted"> (leído {m.dosis_valor})</span>} {m.via ?? ""} {m.frecuencia ?? ""}</li>
                        ))}
                      </ul>
                    </td>
                    <td>
                      {r.alto_riesgo && <span className="tag critico">alto riesgo</span>}{" "}
                      {r.control_especial && <span className="tag urgente">control especial</span>}
                      {!r.alto_riesgo && !r.control_especial && <span className="muted">—</span>}
                    </td>
                    <td>
                      <strong>{hechas} de {r.verificaciones_requeridas}</strong>
                      {r.verificaciones.length > 0 && <span className="secundaria">{r.verificaciones.map((v) => v.usuario).join(", ")}</span>}
                    </td>
                    <td>
                      <button type="button" disabled={!yo || yaFirme} onClick={() => verificar(r.documento_id)}>{siguiente}</button>
                      {yaFirme && <span className="secundaria">Requiere otra persona: la primera verificación la hizo usted (RN-J6).</span>}
                    </td>
                  </tr>
                );
              })}
              {recetas && recetas.length === 0 && <tr><td colSpan={5} className="muted" style={{ textAlign: "center", padding: 24 }}>No hay recetas por verificar.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
