import { CheckCircle2, CircleAlert } from "lucide-react";

import { ErrorApi } from "../api";

export interface Mensaje {
  texto: string;
  error?: boolean;
}

/** Texto de error para una persona: el detalle del backend, sin el código HTTP delante. */
export function textoDeError(e: unknown, respaldo = "No hay conexión con el servidor. Revisa la red y vuelve a intentarlo."): string {
  return e instanceof ErrorApi ? e.detalle : respaldo;
}

/**
 * Resultado de una acción. El éxito se anuncia con cortesía (status); el error interrumpe (alert)
 * y se ve distinto, para que nadie confunda "no se guardó" con "se guardó".
 */
export function EstadoMensaje({ mensaje }: { mensaje: Mensaje | null }) {
  return (
    <>
      <div role="status" aria-live="polite">
        {mensaje && !mensaje.error && <p className="estado-carga ok-estado"><CheckCircle2 size={16} aria-hidden="true" />{mensaje.texto}</p>}
      </div>
      {mensaje?.error && <p className="estado-carga error" role="alert"><CircleAlert size={16} aria-hidden="true" />{mensaje.texto}</p>}
    </>
  );
}
