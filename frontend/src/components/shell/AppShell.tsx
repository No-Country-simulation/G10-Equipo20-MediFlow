import { KeyRound, BarChart3, BellRing, ClipboardCheck, Contact, Contrast, FileCheck2, FileText, Home, LogIn, LogOut, Menu, Monitor, PanelLeftOpen, Pill, Send, SlidersHorizontal, Users, X, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { colaRevision, listarAlertas } from "../../api";
import { useAltoContraste } from "../../app/contraste";
import { ProveedorPared, useEstadoPared } from "../../app/pared";
import { useRol } from "../../app/RolContext";
import { ROLES, rolPuedeVer, type RolId } from "../../app/roles";
import { useSesion } from "../../app/sesion";
import { useUsuario } from "../../app/usuario";
import { BannerAlertas } from "./BannerAlertas";

const INTERVALO_MS = 30_000;

const ICONOS: Record<string, LucideIcon> = {
  "/inicio": Home,
  "/documentos": FileText,
  "/revision": ClipboardCheck,
  "/alertas": BellRing,
  "/farmacia": Pill,
  "/autorizaciones": FileCheck2,
  "/entregas": Send,
  "/pacientes": Contact,
  "/configuracion": SlidersHorizontal,
  "/metricas": BarChart3,
  "/administracion": Users,
};

export function AppShell() {
  const { rol, cambiarRol } = useRol();
  const { cuenta, salir, exigida, nombreSede } = useSesion();
  const [usuario, setUsuario] = useUsuario();
  const navigate = useNavigate();
  const location = useLocation();
  const [contadores, setContadores] = useState({ revision: 0, alertas: 0 });
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [altoContraste, alternarContraste] = useAltoContraste(rol.altoContraste, rol.id);
  const pared = useEstadoPared(rol);

  useEffect(() => {
    if (!rol.veDocumentos) return;
    let activo = true;
    const cargar = () =>
      Promise.all([colaRevision().catch(() => []), listarAlertas({ estado_acuse: "pendiente" }).catch(() => [])]).then(
        ([cola, alertas]) => activo && setContadores({ revision: cola.length, alertas: alertas.length }),
      );
    cargar();
    const id = setInterval(cargar, INTERVALO_MS);
    return () => {
      activo = false;
      clearInterval(id);
    };
  }, [location.pathname, rol.veDocumentos]);

  // En pantallas angostas el menú se cierra al navegar.
  useEffect(() => { setMenuAbierto(false); }, [location.pathname]);

  function alCambiarRol(id: RolId) {
    cambiarRol(id);
    const destino = ROLES.find((r) => r.id === id)?.rutaInicial ?? "/documentos";
    navigate(destino);
  }

  async function alSalir() {
    await salir();
    navigate("/ingresar");
  }

  const permitido = rolPuedeVer(rol, location.pathname);
  // En la pared, la pantalla de alertas es el inicio: el tablero de escritorio no se lee a dos metros.
  const paredDeAlertas = pared.activo && rolPuedeVer(rol, "/alertas");
  const navegacion = paredDeAlertas ? rol.navegacion.filter((item) => item.ruta !== "/inicio") : rol.navegacion;
  const alertasDelMenu = rolPuedeVer(rol, "/alertas") ? contadores.alertas : 0;
  const nombreMenu = menuAbierto
    ? "Cerrar menú"
    : alertasDelMenu > 0
      ? `Abrir menú, ${alertasDelMenu === 1 ? "1 alerta crítica sin acuse" : `${alertasDelMenu} alertas críticas sin acuse`}`
      : "Abrir menú";

  const interruptorContraste = (
    <label className="interruptor-lateral">
      <input type="checkbox" role="switch" checked={altoContraste} onChange={alternarContraste} />
      <Contrast size={16} aria-hidden="true" />
      <span className="texto-lateral">Alto contraste</span>
    </label>
  );

  return (
    <ProveedorPared value={pared}>
      <div className={`shell ${pared.activo ? "pared" : ""}`}>
        <aside className={`lateral ${menuAbierto ? "abierta" : ""}`}>
          <div className="logo">
            <img src="/logo.jpg" alt="MediFlow" />
            <div className="texto-lateral">
              <strong>Medi<span>Flow</span></strong>
              <small>Pack Colombia · {nombreSede || "Sede principal"}</small>
            </div>
            <button type="button" className="hamburguesa" aria-label={nombreMenu} aria-expanded={menuAbierto} aria-controls="menu-principal" onClick={() => setMenuAbierto((v) => !v)}>
              {menuAbierto ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
              {!menuAbierto && alertasDelMenu > 0 && <span className="contador critico" aria-hidden="true">{alertasDelMenu}</span>}
            </button>
          </div>
          <nav id="menu-principal" aria-label="Principal">
            {navegacion.map((item) => {
              const Icono = ICONOS[item.ruta];
              return (
                <NavLink key={item.ruta} to={item.ruta} className={({ isActive }) => (isActive ? "activo" : "")}>
                  {Icono && <Icono size={18} aria-hidden="true" />}
                  <span className="etiqueta">{item.etiqueta}</span>
                  {item.contador === "revision" && contadores.revision > 0 && <span className="contador">{contadores.revision}</span>}
                  {item.contador === "alertas" && contadores.alertas > 0 && <span className="contador critico">{contadores.alertas}</span>}
                </NavLink>
              );
            })}
          </nav>
          {pared.activo ? (
            <div className="usuario usuario-pared">
              {interruptorContraste}
              <button type="button" className="boton-lateral" onClick={pared.alternar}>
                <PanelLeftOpen size={18} aria-hidden="true" /><span className="texto-lateral">Salir de la vista de pared</span>
              </button>
            </div>
          ) : (
            <>
              {!exigida && <NavLink to="/demo" className="demo">Modo demostración ›</NavLink>}
              <div className="usuario">
                {cuenta ? (
                  <div className="sesion-activa" data-testid="sesion-activa">
                    <strong>{cuenta.nombre}</strong>
                    <small>{rol.nombre} · {cuenta.usuario}</small>
                    <NavLink to="/cambiar-clave" className="enlace-sesion"><KeyRound size={16} aria-hidden="true" />Cambiar mi clave</NavLink>
                    <button type="button" className="boton-lateral" onClick={alSalir}><LogOut size={16} aria-hidden="true" />Cerrar sesión</button>
                  </div>
                ) : (
                  <>
                    <label>
                      Rol
                      <select id="selector-rol" value={rol.id} onChange={(e) => alCambiarRol(e.target.value as RolId)}>
                        {ROLES.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
                      </select>
                    </label>
                    <label>
                      Firmo como
                      <input id="firmo-como" value={usuario} onChange={(e) => setUsuario(e.target.value)} placeholder="nombre.apellido" autoComplete="off" />
                    </label>
                    <NavLink to="/ingresar" className="enlace-sesion"><LogIn size={16} aria-hidden="true" />Iniciar sesión</NavLink>
                  </>
                )}
                {interruptorContraste}
                {rol.pantallaCompartida && (
                  <button type="button" className="boton-lateral" onClick={pared.alternar}><Monitor size={16} aria-hidden="true" />Vista de pared</button>
                )}
              </div>
            </>
          )}
        </aside>
        <main className="contenido">
          {rol.veDocumentos && location.pathname !== "/alertas" && <BannerAlertas />}
          {permitido ? (
            paredDeAlertas && location.pathname === "/inicio" ? <Navigate to="/alertas" replace /> : <Outlet />
          ) : (
            <section className="tarjeta" style={{ marginTop: 16 }}>
              <h1>Sin acceso para este rol</h1>
              <p className="muted">
                {rol.nombre} no ve esta sección. Quien configura no revisa y quien administra no ve datos clínicos. Elige otra opción de la barra lateral{cuenta ? "" : " o cambia de rol"}.
              </p>
            </section>
          )}
        </main>
      </div>
    </ProveedorPared>
  );
}
