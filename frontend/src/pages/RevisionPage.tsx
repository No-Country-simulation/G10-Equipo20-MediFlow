import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { colaRevision } from "../api";
import { etiquetaMotivo } from "../app/mensajes";
import { calcularPlazo } from "../app/plazos";
import { ChipPlazo, TagPrioridad } from "../components/Tags";
import type { ItemCola } from "../types";

/** Cola de revisión humana: el backend ya la entrega ordenada por prioridad y antigüedad (RN-J1). */
export function RevisionPage() {
  const [cola, setCola] = useState<ItemCola[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    colaRevision().then(setCola).catch(() => setError("No hay conexión con la API."));
  }, []);

  return (
    <>
      <header className="encabezado">
        <div>
          <h1>Cola de revisión</h1>
          <p className="sub">Por prioridad clínica y luego por antigüedad (RN-J1). Plazos: Crítico 15 min, Urgente 2 h, Rutina 24 h hábiles (RN-J2). Abre un caso y usa J y K para recorrer la cola.</p>
        </div>
      </header>
      {error && <p className="error">{error}</p>}
      <section className="tarjeta" style={{ padding: 0 }}>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Documento</th><th>Tipo</th><th>Prioridad</th><th>Motivo</th><th>Plazo</th><th></th></tr></thead>
            <tbody>
              {cola?.map((item) => (
                <tr key={`${item.documento_id}-${item.version}`} data-testid="fila-cola" className={`fila ${item.nivel_prioridad === "Crítico" ? "critico" : item.nivel_prioridad === "Urgente" ? "urgente" : "rutina"}`}>
                  <td><code>{item.documento_id}</code></td>
                  <td>{item.tipo ?? <span className="muted">—</span>}</td>
                  <td><TagPrioridad nivel={item.nivel_prioridad} /></td>
                  <td>{etiquetaMotivo(item.motivo_auditoria)}{item.campos_dudosos.length > 0 && <span className="secundaria">Dudosos: {item.campos_dudosos.join(", ")}</span>}</td>
                  <td><ChipPlazo plazo={calcularPlazo(item.creado_en, item.plazo_minutos)} /></td>
                  <td><Link to={`/documentos/${encodeURIComponent(item.documento_id)}?cola=1`}>Revisar ›</Link></td>
                </tr>
              ))}
              {cola && cola.length === 0 && <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 24 }}>No hay documentos en revisión.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
