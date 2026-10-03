import { KeyRound } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { rolPorId } from "../app/roles";
import { useSesion } from "../app/sesion";
import { EstadoMensaje, textoDeError, type Mensaje } from "../components/EstadoMensaje";

/**
 * Cambio de la propia clave. Es obligatorio cuando la clave la puso otra persona (administrador o instalación):
 * hasta cambiarla no se ve nada más. También se puede hacer en cualquier momento desde la barra lateral.
 */
export function CambiarClavePage({ obligatorio = false }: { obligatorio?: boolean }) {
  const { cuenta, cambiarClave, salir } = useSesion();
  const navigate = useNavigate();
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [mensaje, setMensaje] = useState<Mensaje | null>(null);

  const distintas = nueva.length > 0 && confirmacion.length > 0 && nueva !== confirmacion;

  async function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (nueva !== confirmacion) {
      setMensaje({ texto: "La confirmación no coincide con la clave nueva.", error: true });
      return;
    }
    setEnviando(true);
    setMensaje(null);
    try {
      const actualizada = await cambiarClave(actual, nueva);
      navigate(rolPorId(actualizada.rol).rutaInicial, { replace: true });
    } catch (e) {
      setActual("");
      setMensaje({ texto: textoDeError(e), error: true });
      setEnviando(false);
    }
  }

  return (
    <main className="ingreso">
      <section className="tarjeta" data-testid="cambiar-clave">
        <img src="/logo.jpg" alt="" width={56} height={56} />
        <h1>{obligatorio ? "Elige tu clave" : "Cambiar mi clave"}</h1>
        <p className="muted">
          {obligatorio
            ? <>La clave de <strong>{cuenta?.usuario}</strong> la definió otra persona. Antes de seguir, elige una que solo tú conozcas.</>
            : <>Al cambiarla se cierran tus otras sesiones abiertas. Esta sigue activa.</>}
        </p>
        <form onSubmit={alEnviar}>
          <label>Clave actual<input type="password" value={actual} onChange={(e) => setActual(e.target.value)} autoComplete="current-password" required /></label>
          <label>Clave nueva<input type="password" value={nueva} onChange={(e) => setNueva(e.target.value)} autoComplete="new-password" required aria-describedby="politica-clave" /></label>
          <label>Confirmar clave nueva<input type="password" value={confirmacion} onChange={(e) => setConfirmacion(e.target.value)} autoComplete="new-password" required aria-invalid={distintas || undefined} /></label>
          <p id="politica-clave" className="muted pista">Al menos 10 caracteres, con letras y números, y distinta de tu usuario.</p>
          <button type="submit" disabled={enviando || !actual || !nueva || !confirmacion}><KeyRound size={16} aria-hidden="true" />{enviando ? "Guardando…" : "Guardar clave"}</button>
        </form>
        <EstadoMensaje mensaje={mensaje} />
        <p className="muted pie-ingreso">
          {obligatorio
            ? <button type="button" className="enlace" onClick={() => void salir()}>Salir sin cambiarla</button>
            : <button type="button" className="enlace" onClick={() => navigate(-1)}>Volver</button>}
        </p>
      </section>
    </main>
  );
}
