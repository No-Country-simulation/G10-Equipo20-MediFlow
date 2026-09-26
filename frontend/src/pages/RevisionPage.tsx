import { ClipboardCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { colaRevision } from "../api";
import { etiquetaMotivo, etiquetaTipo, tituloHallazgos } from "../app/mensajes";
import { calcularPlazo } from "../app/plazos";
import { AvisoSistemaDegradado, conPunto, horaCorta } from "../components/AvisoSistema";
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
          <td>
            <span className="principal">{tituloHallazgos(item.hallazgos) || etiquetaTipo(item.tipo) || "Sin clasificar"}</span>
            <span className="secundaria">
              <Link to={`/documentos/${encodeURIComponent(item.documento_id)}?cola=1`} aria-label={`Revisar ${item.documento_id}`}><code>{item.documento_id}</code></Link>
              {(item.hallazgos?.length ?? 0) > 0 && item.tipo && <> · {etiquetaTipo(item.tipo)}</>}
            </span>
          </td>
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
  return <thead><tr><th>Caso</th><th>Prioridad</th><th>Motivo</th><th>Plazo</th><th><span className="oculto-visual">Abrir</span></th></tr></thead>;
}

/**
 * Cola de revisión humana: el backend ya la entrega ordenada por prioridad y antigüedad (RN-J1).
 * Cuando muchos casos comparten el fallo técnico, se explica la causa una vez y se agrupan los no críticos,
 * para que lo que necesita criterio clínico no quede enterrado. Un Crítico nunca se pliega.
 */
export function RevisionPage() {
  const [cola, setCola] = useState<ItemCola[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    colaRevision().then(setCola).catch(() => setError("No hay conexión con la API. La cola se mostrará cuando vuelva."));
  }, []);

  const esFallo = (c: ItemCola) => c.motivo_auditoria === "fallo_tecnico";
  const porFallo = (cola ?? []).filter(esFallo);
  const degradado = porFallo.length >= UMBRAL_SISTEMA_DEGRADADO;
  const plegables = degradado ? porFallo.filter((c) => c.nivel_prioridad !== "Crítico") : [];
  const principales = degradado ? (cola ?? []).filter((c) => !esFallo(c) || c.nivel_prioridad === "Crítico") : cola ?? [];
  const criticosFallo = porFallo.length - plegables.length;
  const desde = porFallo.reduce<string | null>((min, c) => (min === null || c.creado_en < min ? c.creado_en : min), null);

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
        <AvisoSistemaDegradado titulo={conPunto(`El motor de extracción no está respondiendo${desde ? ` desde las ${horaCorta(desde)}` : ""}`)}>
          <p>{porFallo.length} documentos pasaron a revisión manual por esa sola causa.{criticosFallo > 0 && ` ${criticosFallo === 1 ? "El crítico queda" : `Los ${criticosFallo} críticos quedan`} arriba, en la cola.`} La detección de hallazgos críticos por texto sigue activa y sus alertas salen igual.</p>
        </AvisoSistemaDegradado>
      )}

      {(principales.length > 0 || !degradado) && (
        <section className="tarjeta" style={{ padding: 0 }}>
          <div className="scroll">
            <table className="tabla-densa">
              <Cabecera />
              <tbody>
                <Filas items={principales} />
                {cola && cola.length === 0 && <tr><td colSpan={5}><Vacio icono={ClipboardCheck} titulo="Cola vacía" texto="Nada espera revisión humana. Lo que el sistema no pueda decidir solo llegará aquí con su motivo." /></td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {plegables.length > 0 && (
        <details className="tarjeta grupo" data-testid="grupo-fallo-tecnico" open={principales.length === 0}>
          <summary>
            <strong>{plegables.length} documentos por fallo técnico</strong>
            <span className="muted"> · sin críticos · revisión manual del documento completo</span>
          </summary>
          <div className="scroll">
            <table className="tabla-densa">
              <Cabecera />
              <tbody><Filas items={plegables} /></tbody>
            </table>
          </div>
        </details>
      )}
    </>
  );
}
