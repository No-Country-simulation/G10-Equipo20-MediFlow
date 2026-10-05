import { LogIn } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { rolPorId } from "../app/roles";
import { useSesion } from "../app/sesion";
import { EstadoMensaje, textoDeError, type Mensaje } from "../components/EstadoMensaje";

/** Inicio de sesión del personal (RN-K5). Las cuentas y sus claves las crea el administrador. */
export function IngresarPage() {
  const { cuenta, exigida, ingresar } = useSesion();
  const navigate = useNavigate();
  const [usuario, setUsuario] = useState("");
  const [clave, setClave] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [mensaje, setMensaje] = useState<Mensaje | null>(null);

  async function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    setEnviando(true);
    setMensaje(null);
    try {
      await ingresar(usuario.trim(), clave, (nueva) => navigate(rolPorId(nueva.rol).rutaInicial, { replace: true }));
    } catch (e) {
      setClave("");
      setMensaje({ texto: textoDeError(e), error: true });
      setEnviando(false);
    }
  }

  return (
    <main className="ingreso">
      <section className="tarjeta">
        <img src="/logo.jpg" alt="" width={56} height={56} />
        <h1>Iniciar sesión en MediFlow</h1>
        {cuenta ? (
          <>
            <p>Ya iniciaste sesión como <strong>{cuenta.nombre}</strong> ({rolPorId(cuenta.rol).nombre}).</p>
            <p><Link to={rolPorId(cuenta.rol).rutaInicial}>Ir a mi inicio ›</Link></p>
          </>
        ) : (
          <>
            <p className="muted">
              Con tu sesión, cada acuse, verificación y corrección queda firmado con tu cuenta, y solo ves lo que tu rol necesita.
            </p>
            <form onSubmit={alEnviar}>
              <label>Usuario<input value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="username" placeholder="nombre.apellido" required /></label>
              <label>Clave<input type="password" value={clave} onChange={(e) => setClave(e.target.value)} autoComplete="current-password" required /></label>
              <button type="submit" disabled={enviando || !usuario.trim() || !clave}><LogIn size={16} aria-hidden="true" />{enviando ? "Ingresando…" : "Ingresar"}</button>
            </form>
            <EstadoMensaje mensaje={mensaje} />
            <p className="muted pie-ingreso">
              ¿Sin cuenta o sin clave? La define el administrador del sistema.
              {!exigida && <> <Link to="/inicio">Seguir sin sesión (demostración) ›</Link></>}
            </p>
          </>
        )}
      </section>
    </main>
  );
}
