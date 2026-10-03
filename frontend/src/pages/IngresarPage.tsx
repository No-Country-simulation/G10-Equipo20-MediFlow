import { LogIn, ShieldPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { rolPorId } from "../app/roles";
import { useSesion } from "../app/sesion";
import { EstadoMensaje, textoDeError, type Mensaje } from "../components/EstadoMensaje";

/** Inicio de sesión del personal (RN-K5). Las cuentas y sus claves las crea el administrador. */
export function IngresarPage() {
  const { cuenta, exigida, sinCuentas, ingresar, crearPrimerAdministrador } = useSesion();
  const navigate = useNavigate();
  const [usuario, setUsuario] = useState("");
  const [nombre, setNombre] = useState("");
  const [clave, setClave] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [mensaje, setMensaje] = useState<Mensaje | null>(null);

  async function alCrearPrimero(evento: FormEvent) {
    evento.preventDefault();
    if (clave !== confirmacion) {
      setMensaje({ texto: "La confirmación no coincide con la clave.", error: true });
      return;
    }
    setEnviando(true);
    setMensaje(null);
    try {
      const nueva = await crearPrimerAdministrador(usuario.trim(), nombre.trim(), clave);
      navigate(rolPorId(nueva.rol).rutaInicial, { replace: true });
    } catch (e) {
      setMensaje({ texto: textoDeError(e), error: true });
      setEnviando(false);
    }
  }

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
        <h1>{sinCuentas && !cuenta ? "Primer administrador de MediFlow" : "Iniciar sesión en MediFlow"}</h1>
        {sinCuentas && !cuenta ? (
          <form onSubmit={alCrearPrimero} data-testid="primer-administrador">
            <p className="muted">
              Esta instalación todavía no tiene cuentas. La primera es la del administrador del sistema, que después crea
              las demás desde Administración. Esta opción desaparece en cuanto exista una cuenta.
            </p>
            <label>Usuario<input value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="username" placeholder="nombre.apellido" required /></label>
            <label>Nombre<input value={nombre} onChange={(e) => setNombre(e.target.value)} autoComplete="name" required /></label>
            <label>Clave<input type="password" value={clave} onChange={(e) => setClave(e.target.value)} autoComplete="new-password" required aria-describedby="politica-clave" /></label>
            <label>Confirmar clave<input type="password" value={confirmacion} onChange={(e) => setConfirmacion(e.target.value)} autoComplete="new-password" required /></label>
            <p id="politica-clave" className="muted pista">Al menos 10 caracteres, con letras y números, y distinta del usuario.</p>
            <button type="submit" disabled={enviando || !usuario.trim() || !nombre.trim() || !clave || !confirmacion}><ShieldPlus size={16} aria-hidden="true" />{enviando ? "Creando…" : "Crear la cuenta de administrador"}</button>
            <EstadoMensaje mensaje={mensaje} />
          </form>
        ) : cuenta ? (
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
