import { useState } from "react";

import { confirmarEntrega, ErrorApi } from "../../api";
import type { DocumentoDetalle, EstadoDocumento } from "../../types";

interface Props {
  detalle: DocumentoDetalle;
  onReiniciar: () => void;
}

/** Pantalla 6: entrega a destinos y cierre (sección 3.3: Enrutado frente a Entregado; RN-J7). */
export function EntregaScreen({ detalle, onReiniciar }: Props) {
  const en = detalle.resultado?.enrutamiento;
  const [entregas, setEntregas] = useState<Record<string, boolean>>(detalle.entregas ?? {});
  const [pendientes, setPendientes] = useState<string[] | null>(null);
  const [estado, setEstado] = useState<EstadoDocumento>(detalle.estado);
  const [error, setError] = useState<string | null>(null);

  if (!en) {
    return <section className="pantalla"><h2>6. Entrega</h2><p>Sin plan de enrutamiento.</p></section>;
  }
  const plan = [en.destino_principal, ...en.destinos_secundarios];
  const retenidas = en.entregas_retenidas;

  async function confirmar(destino: string) {
    setError(null);
    try {
      const r = await confirmarEntrega(detalle.documento_id, destino);
      setEntregas(r.entregas);
      setPendientes(r.pendientes);
      setEstado(r.estado);
    } catch (e) {
      setError(e instanceof ErrorApi ? `${e.status}: ${e.detalle}` : String(e));
    }
  }

  return (
    <section className="pantalla">
      <h2>6. Entrega</h2>
      <p>Estado: <strong className={estado === "ENTREGADO" ? "ok" : ""}>{estado}</strong></p>
      <ul className="destinos">
        {plan.map((destino) => (
          <li key={destino}>
            <strong>{destino}</strong>
            {en.motivos_destino[destino] && <span className="muted"> · {en.motivos_destino[destino]}</span>}
            {retenidas[destino] ? (
              <span className="aviso"> · retenida: {retenidas[destino]}</span>
            ) : entregas[destino] ? (
              <span className="ok"> · confirmada</span>
            ) : (
              <button type="button" className="secundario" onClick={() => confirmar(destino)}>Confirmar {destino}</button>
            )}
          </li>
        ))}
      </ul>
      {pendientes && pendientes.length > 0 && (
        <p className="aviso">Pendiente para cerrar: {pendientes.join(", ")}</p>
      )}
      {estado === "ENTREGADO" && <p className="ok">Documento entregado. Estado final e inmutable (RN-I1).</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <button type="button" onClick={onReiniciar}>Nuevo documento</button>
    </section>
  );
}
