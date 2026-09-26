import { BellRing, UserCheck } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { acusarAlerta, ErrorApi } from "../api";
import { useRol } from "../app/RolContext";
import { useUsuario } from "../app/usuario";

type RespuestaAcuse = Awaited<ReturnType<typeof acusarAlerta>>;

/**
 * Acuse de una alerta crítica (RN-J7, RN-Q5). El botón siempre responde: pregunta quién da el acuse
 * en el momento. En una pantalla compartida no propone ninguna firma, para que cada acuse lleve a la persona real.
 */
export function AccionAcuse({ documentoId, contexto, onAcusado }: {
  documentoId: string;
  /** Qué se acusa, para quien no ve la fila: "Infarto con elevación del ST, FM-2024-0119". */
  contexto?: string;
  onAcusado: (r: RespuestaAcuse) => void;
}) {
  const { rol } = useRol();
  const [firma] = useUsuario();
  const [abierto, setAbierto] = useState(false);
  const [nombre, setNombre] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const campo = useRef<HTMLInputElement>(null);
  const id = useId();

  useEffect(() => { if (abierto) campo.current?.focus(); }, [abierto]);

  function abrir() {
    setNombre(rol.pantallaCompartida ? "" : firma.trim());
    setError(null);
    setAbierto(true);
  }

  async function confirmar(e?: FormEvent) {
    e?.preventDefault();
    if (!nombre.trim() || enviando) return;
    setEnviando(true);
    setError(null);
    try {
      const r = await acusarAlerta(documentoId, nombre.trim());
      setAbierto(false);
      onAcusado(r);
    } catch (err) {
      setError(err instanceof ErrorApi ? err.detalle : "No se pudo registrar el acuse. Revisa la conexión y vuelve a intentarlo.");
    } finally {
      setEnviando(false);
    }
  }

  if (!abierto) {
    return <button type="button" onClick={abrir} aria-label={`Dar acuse: ${contexto ?? documentoId}`}><BellRing size={16} aria-hidden="true" />Dar acuse</button>;
  }
  return (
    <form className="acuse" onSubmit={confirmar} onKeyDown={(e) => { if (e.key === "Escape") setAbierto(false); }}>
      <label htmlFor={`${id}-quien`}>¿Quién da el acuse?</label>
      <span className="pista">{contexto ?? documentoId}</span>
      <input id={`${id}-quien`} ref={campo} value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="nombre.apellido" autoComplete="off" />
      <div className="acciones">
        <button type="submit" disabled={!nombre.trim() || enviando}><UserCheck size={16} aria-hidden="true" />{enviando ? "Registrando…" : "Confirmar acuse"}</button>
        <button type="button" className="secundario" onClick={() => setAbierto(false)}>Cancelar</button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </form>
  );
}
