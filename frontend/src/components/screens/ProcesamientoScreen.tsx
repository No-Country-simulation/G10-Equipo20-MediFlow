import type { DocumentoDetalle } from "../../types";

interface Props {
  detalle: DocumentoDetalle;
  onContinuar: () => void;
}

/** Pantalla 2: ciclo de vida recorrido (sección 3, RN-I3). */
export function ProcesamientoScreen({ detalle, onContinuar }: Props) {
  const transiciones = detalle.transiciones ?? [];
  return (
    <section className="pantalla">
      <h2>2. Procesamiento</h2>
      <p>
        Documento <code>{detalle.documento_id}</code> (versión {detalle.version}) · estado actual <strong>{detalle.estado}</strong>
        {detalle.posible_duplicado_de && <> · posible duplicado de <code>{detalle.posible_duplicado_de}</code> (RN-O3)</>}
      </p>
      <ol className="timeline">
        {transiciones.map((t, i) => (
          <li key={i} data-testid="transicion">
            <span className="estado">{t.a_estado}</span>
            <span className="muted"> · {t.actor} · {new Date(t.fecha_hora).toLocaleTimeString("es-CO")}</span>
            <div className="motivo">{t.motivo}</div>
          </li>
        ))}
      </ol>
      <p className="muted">
        Respaldo del original: {detalle.status_backup} {detalle.ruta_storage && <code>{detalle.ruta_storage}</code>}
      </p>
      <button type="button" onClick={onContinuar}>Ver cockpit</button>
    </section>
  );
}
