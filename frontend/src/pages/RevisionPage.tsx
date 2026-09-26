import { ClipboardCheck, ServerCrash } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { colaRevision } from "../api";
import { etiquetaMotivo } from "../app/mensajes";
import { calcularPlazo } from "../app/plazos";
import { ChipPlazo, TagPrioridad } from "../components/Tags";
import { Vacio } from "../components/Vacio";
import type { ItemCola } from "../types";

/** Desde cuántos casos por fallo técnico se trata como una caída del motor y no como casos sueltos. */
const UMBRAL_SISTEMA_DEGRADADO = 3;

function Filas({ items }: { items: ItemCola[] }) {
  return (
    <>
      {items.map((item) => (
        <tr key={`${item.documento_id}-${item.version}`} data-testid="fila-cola" className={`fila ${item.nivel_prioridad === "Crítico" ? "critico" : item.nivel_prioridad === "Urgente" ? "urgente" : "rutina"}`}>
          <td><Link to={`/documentos/${encodeURIComponent(item.documento_id)}?cola=1`} aria-label={`Revisar ${item.documento_id}`}><code>{item.documento_id}</code></Link></td>
          <td>{item.tipo ?? <span className="muted">—</span>}</td>
          <td><TagPrioridad nivel={item.nivel_prioridad} /></td>
          <td>{etiquetaMotivo(item.motivo_auditoria)}{item.campos_dudosos.length > 0 && <span className="secundaria">Dudosos: {item.campos_dudosos.join(", ")}</span>}</td>
          <td><ChipPlazo plazo={calcularPlazo(item.creado_en, item.plazo_minutos)} /></td>
          <td><Link to={`/documentos/${encodeURIComponent(item.documento_id)}?cola=1`} aria-hidden="true" tabIndex={-1}>Revisar ›</Link></td>
        </tr>
      ))}
    </>
  );
}

function Cabecera() {
  return <thead><tr><th>Documento</th><th>Tipo</th><th>Prioridad</th><th>Motivo</th><th>Plazo</th><th><span className="oculto-visual">Abrir</span></th></tr></thead>;
}

/**
 * Cola de revisión humana: el backend ya la entrega ordenada por prioridad y antigüedad (RN-J1).
 * Cuando muchos casos comparten el fallo técnico, se explica la causa una vez y se agrupan, para que
 * lo que sí necesita criterio clínico no quede enterrado bajo filas rojas iguales.
 */
export function RevisionPage() {
  const [cola, setCola] = useState<ItemCola[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    colaRevision().then(setCola).catch(() => setError("No hay conexión con la API. La cola se mostrará cuando vuelva."));
  }, []);

  const porFallo = (cola ?? []).filter((c) => c.motivo_auditoria === "fallo_tecnico");
  const degradado = porFallo.length >= UMBRAL_SISTEMA_DEGRADADO;
  const principales = degradado ? (cola ?? []).filter((c) => c.motivo_auditoria !== "fallo_tecnico") : cola ?? [];
  const criticosFallo = porFallo.filter((c) => c.nivel_prioridad === "Crítico").length;

  return (
    <>
      <header className="encabezado">
        <div>
          <h1>Cola de revisión</h1>
          <p className="sub">Ordenada por prioridad clínica y luego por antigüedad. Plazos: Crítico 15 min, Urgente 2 h, Rutina 24 h hábiles. Abre un caso y usa J y K para recorrer la cola.</p>
        </div>
      </header>
      {error && <p className="error">{error}</p>}

      {degradado && (
        <section className="aviso-sistema" data-testid="sistema-degradado">
          <ServerCrash size={22} aria-hidden="true" />
          <div>
            <strong>El motor de extracción no está respondiendo.</strong>
            <p>{porFallo.length} documentos pasaron a revisión manual por esa sola causa. La detección de hallazgos críticos por texto sigue activa y sus alertas salen igual. Cuando el motor vuelva, se pueden reprocesar.</p>
          </div>
        </section>
      )}

      {(principales.length > 0 || !degradado) && (
        <section className="tarjeta" style={{ padding: 0 }}>
          <div className="scroll">
            <table className="tabla-densa">
              <Cabecera />
              <tbody>
                <Filas items={principales} />
                {cola && cola.length === 0 && <tr><td colSpan={6}><Vacio icono={ClipboardCheck} titulo="Cola vacía" texto="Nada espera revisión humana. Lo que el sistema no pueda decidir solo llegará aquí con su motivo." /></td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {degradado && (
        <details className="tarjeta grupo" data-testid="grupo-fallo-tecnico">
          <summary>
            <strong>{porFallo.length} documentos por fallo técnico</strong>
            <span className="muted"> · {criticosFallo === 1 ? "1 crítico" : `${criticosFallo} críticos`} · revisión manual del documento completo</span>
          </summary>
          <div className="scroll">
            <table className="tabla-densa">
              <Cabecera />
              <tbody><Filas items={porFallo} /></tbody>
            </table>
          </div>
        </details>
      )}
    </>
  );
}
