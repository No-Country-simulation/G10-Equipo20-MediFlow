import { BarChart3, BellRing, ClipboardCheck, Contrast, FileCheck2, FileText, Home, Menu, Pill, Send, SlidersHorizontal, Users, X, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { colaRevision, listarAlertas } from "../../api";
import { useAltoContraste } from "../../app/contraste";
import { useRol } from "../../app/RolContext";
import { ROLES, rolPuedeVer, type RolId } from "../../app/roles";
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
  "/configuracion": SlidersHorizontal,
  "/metricas": BarChart3,
  "/administracion": Users,
};

export function AppShell() {
  const { rol, cambiarRol } = useRol();
  const [usuario, setUsuario] = useUsuario();
  const navigate = useNavigate();
  const location = useLocation();
  const [contadores, setContadores] = useState({ revision: 0, alertas: 0 });
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [altoContraste, alternarContraste] = useAltoContraste(rol.altoContraste);

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

  const permitido = rolPuedeVer(rol, location.pathname);
  const pendientes = contadores.revision + contadores.alertas;

  return (
    <div className="shell">
      <aside className={`lateral ${menuAbierto ? "abierta" : ""}`}>
        <div className="logo">
          <img src="/logo.jpg" alt="MediFlow" />
          <div>
            <strong>Medi<span>Flow</span></strong>
            <small>Pack Colombia · Sede demo</small>
          </div>
          <button type="button" className="hamburguesa" aria-label={menuAbierto ? "Cerrar menú" : "Abrir menú"} aria-expanded={menuAbierto} aria-controls="menu-principal" onClick={() => setMenuAbierto((v) => !v)}>
            {menuAbierto ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
            {!menuAbierto && rol.veDocumentos && pendientes > 0 && <span className="contador critico">{pendientes}</span>}
          </button>
        </div>
        <nav id="menu-principal" aria-label="Principal">
          {rol.navegacion.map((item) => {
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
        <NavLink to="/demo" className="demo">Modo demostración ›</NavLink>
        <div className="usuario">
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
          <label className="interruptor-lateral">
            <input type="checkbox" role="switch" checked={altoContraste} onChange={alternarContraste} />
            <Contrast size={16} aria-hidden="true" />
            Alto contraste
          </label>
        </div>
      </aside>
      <main className="contenido">
        {rol.veDocumentos && location.pathname !== "/alertas" && <BannerAlertas />}
        {permitido ? (
          <Outlet />
        ) : (
          <section className="tarjeta" style={{ marginTop: 16 }}>
            <h1>Sin acceso para este rol</h1>
            <p className="muted">
              {rol.nombre} no ve esta sección. Quien configura no revisa y quien administra no ve datos clínicos. Elige otra opción de la barra lateral o cambia de rol.
            </p>
          </section>
        )}
      </main>
    </div>
  );
}
