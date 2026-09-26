import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { colaRevision, listarAlertas } from "../../api";
import { useRol } from "../../app/RolContext";
import { ROLES, rolPuedeVer, type RolId } from "../../app/roles";
import { BannerAlertas } from "./BannerAlertas";

const INTERVALO_MS = 30_000;

export function AppShell() {
  const { rol, cambiarRol } = useRol();
  const navigate = useNavigate();
  const location = useLocation();
  const [contadores, setContadores] = useState({ revision: 0, alertas: 0 });

  useEffect(() => {
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
  }, [location.pathname]);

  function alCambiarRol(id: RolId) {
    cambiarRol(id);
    const destino = ROLES.find((r) => r.id === id)?.rutaInicial ?? "/documentos";
    navigate(destino);
  }

  const permitido = rolPuedeVer(rol, location.pathname);

  return (
    <div className="shell">
      <aside className="lateral">
        <div className="logo">
          <img src="/logo.jpg" alt="MediFlow" />
          <div>
            <strong>Medi<span>Flow</span></strong>
            <small>Pack Colombia · Sede demo</small>
          </div>
        </div>
        <nav aria-label="Principal">
          {rol.navegacion.map((item) => (
            <NavLink key={item.ruta} to={item.ruta} className={({ isActive }) => (isActive ? "activo" : "")}>
              <span>{item.etiqueta}</span>
              {item.contador === "revision" && contadores.revision > 0 && <span className="contador">{contadores.revision}</span>}
              {item.contador === "alertas" && contadores.alertas > 0 && <span className="contador critico">{contadores.alertas}</span>}
            </NavLink>
          ))}
        </nav>
        <NavLink to="/demo" className="demo">Modo demostración ›</NavLink>
        <div className="usuario">
          <label>
            Rol
            <select id="selector-rol" value={rol.id} onChange={(e) => alCambiarRol(e.target.value as RolId)}>
              {ROLES.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
            </select>
          </label>
          <small>{rol.descripcion}</small>
        </div>
      </aside>
      <main className="contenido">
        <BannerAlertas />
        {permitido ? (
          <Outlet />
        ) : (
          <section className="tarjeta" style={{ marginTop: 16 }}>
            <h1>Sin acceso para este rol</h1>
            <p className="muted">
              {rol.nombre} no ve esta sección (RN-K1, RN-K2). Elige otra opción de la barra lateral o cambia de rol.
            </p>
          </section>
        )}
      </main>
    </div>
  );
}
