import { BellRing, UserCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { acusarAlerta, ErrorApi } from "../api";
import { useUsuario } from "../app/usuario";

type RespuestaAcuse = Awaited<ReturnType<typeof acusarAlerta>>;

/**
 * Acuse de una alerta crítica (RN-J7, RN-Q5). Lo firma la cuenta de la sesión; antes de registrarlo se confirma
 * en línea con el nombre de quien firma, porque en una pantalla compartida la sesión abierta puede no ser la de quien mira.
 */
export function AccionAcuse({ documentoId, contexto, onAcusado }: {
  documentoId: string;
  /** Qué se acusa, para quien no ve la fila: "Infarto con elevación del ST, FM-2024-0119". */
  contexto?: string;
  onAcusado: (r: RespuestaAcuse) => void;
}) {
  const [firma] = useUsuario();
  const [abierto, setAbierto] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const boton = useRef<HTMLButtonElement>(null);

  useEffect(() => { if (abierto) boton.current?.focus(); }, [abierto]);

  async function confirmar() {
    if (enviando) return;
    setEnviando(true);
    setError(null);
    try {
      const r = await acusarAlerta(documentoId);
      setAbierto(false);
      onAcusado(r);
    } catch (err) {
      setError(err instanceof ErrorApi ? err.detalle : "No se pudo registrar el acuse. Revisa la conexión y vuelve a intentarlo.");
    } finally {
      setEnviando(false);
    }
  }

  if (!abierto) {
    return <button type="button" onClick={() => { setError(null); setAbierto(true); }} aria-label={`Dar acuse: ${contexto ?? documentoId}`}><BellRing size={16} aria-hidden="true" />Dar acuse</button>;
  }
  return (
    <div className="acuse" role="group" aria-label={`Confirmar acuse: ${contexto ?? documentoId}`} onKeyDown={(e) => { if (e.key === "Escape") setAbierto(false); }}>
      <p>¿Dar acuse de <strong>{contexto ?? documentoId}</strong> como <strong>{firma}</strong>?</p>
      <div className="acciones">
        <button type="button" ref={boton} onClick={() => void confirmar()} disabled={enviando}><UserCheck size={16} aria-hidden="true" />{enviando ? "Registrando…" : "Confirmar acuse"}</button>
        <button type="button" className="secundario" onClick={() => setAbierto(false)}>Cancelar</button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
