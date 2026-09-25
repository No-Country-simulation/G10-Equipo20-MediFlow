import { useState } from "react";

import { acusarAlerta, ErrorApi } from "../../api";
import type { DocumentoDetalle } from "../../types";

interface Props {
  detalle: DocumentoDetalle;
  onAcusada: () => void;
}

/** Pantalla 4: alerta crítica con acuse (RN-F1, RN-F2, RN-Q4, RN-Q5, RN-J7). */
export function AlertaCriticaScreen({ detalle, onAcusada }: Props) {
  const notificacion = detalle.resultado?.notificacion_generada;
  const [usuario, setUsuario] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function acusar() {
    setEnviando(true);
    setError(null);
    try {
      await acusarAlerta(detalle.documento_id, usuario.trim());
      onAcusada();
    } catch (e) {
      setError(e instanceof ErrorApi ? e.detalle : String(e));
    } finally {
      setEnviando(false);
    }
  }

  if (!notificacion) {
    return (
      <section className="pantalla">
        <h2>4. Alerta</h2>
        <p>Este documento no generó alerta.</p>
        <button type="button" onClick={onAcusada}>Continuar</button>
      </section>
    );
  }

  return (
    <section className="pantalla alerta-critica">
      <h2>4. Alerta crítica</h2>
      <div className="tarjeta alerta">
        <p className="mensaje">{notificacion.mensaje}</p>
        <p className="muted">
          Canal {notificacion.canal} · destinatario {notificacion.destinatario} · emitida {new Date(notificacion.fecha_hora).toLocaleString("es-CO")}
        </p>
        <p className="muted">Sin datos del paciente por diseño (RN-Q4). Sin acuse en 15 minutos escala al siguiente rol (RN-F2).</p>
        {notificacion.enlace && <a href={notificacion.enlace} target="_blank" rel="noreferrer">Abrir en el sistema</a>}
      </div>

      <label>
        Usuario que da el acuse
        <input value={usuario} onChange={(e) => setUsuario(e.target.value)} placeholder="jefe.urgencias" />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <button type="button" disabled={usuario.trim() === "" || enviando} onClick={acusar}>Dar acuse</button>
    </section>
  );
}
