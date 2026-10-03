import { BrowserRouter, MemoryRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "../components/shell/AppShell";
import { AdministracionPage } from "../pages/AdministracionPage";
import { AutorizacionesPage } from "../pages/AutorizacionesPage";
import { CambiarClavePage } from "../pages/CambiarClavePage";
import { ConfiguracionPage } from "../pages/ConfiguracionPage";
import { DetalleDocumentoPage } from "../pages/DetalleDocumentoPage";
import { DocumentosPage } from "../pages/DocumentosPage";
import { EntregasPage } from "../pages/EntregasPage";
import { FarmaciaPage } from "../pages/FarmaciaPage";
import { IngresarPage } from "../pages/IngresarPage";
import { InicioPage } from "../pages/InicioPage";
import { MetricasPage } from "../pages/MetricasPage";
import { PacienteDetallePage } from "../pages/PacienteDetallePage";
import { PacientesPage } from "../pages/PacientesPage";
import { AlertasPage } from "../pages/Placeholders";
import { RevisionPage } from "../pages/RevisionPage";
import { RolProvider } from "./RolContext";
import { ROLES, type RolId } from "./roles";
import { SesionProvider, useSesion } from "./sesion";
import type { CuentaSesion } from "../types";

function Rutas() {
  const { cuenta } = useSesion();
  // RN-K5: sin sesión no se muestra nada más que el ingreso (y, sin cuentas, la creación del primer administrador, RN-S3).
  if (!cuenta) return <IngresarPage />;
  // Una clave puesta por otra persona se cambia antes de ver nada.
  if (cuenta?.debe_cambiar_clave) return <CambiarClavePage obligatorio />;
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/inicio" replace />} />
        <Route path="/inicio" element={<InicioPage />} />
        <Route path="/documentos" element={<DocumentosPage />} />
        <Route path="/documentos/:id" element={<DetalleDocumentoPage />} />
        <Route path="/revision" element={<RevisionPage />} />
        <Route path="/alertas" element={<AlertasPage />} />
        <Route path="/farmacia" element={<FarmaciaPage />} />
        <Route path="/autorizaciones" element={<AutorizacionesPage />} />
        <Route path="/entregas" element={<EntregasPage />} />
        <Route path="/pacientes" element={<PacientesPage />} />
        <Route path="/pacientes/:id" element={<PacienteDetallePage />} />
        <Route path="/configuracion" element={<ConfiguracionPage />} />
        <Route path="/metricas" element={<MetricasPage />} />
        <Route path="/administracion" element={<AdministracionPage />} />
        <Route path="*" element={<Navigate to="/inicio" replace />} />
      </Route>
      <Route path="/cambiar-clave" element={<CambiarClavePage />} />
      <Route path="/ingresar" element={<IngresarPage />} />
    </Routes>
  );
}

/** Sesión de prueba para un rol: una cuenta ficticia con el nombre que usan las pruebas. */
export function cuentaDePrueba(rol: RolId): CuentaSesion {
  const usuarios: Record<RolId, string> = {
    auditor_clinico: "aud.ana", quimico_farmaceutico: "qf.maria", auditor_autorizaciones: "aut.luis",
    jefe_urgencias: "jefe.rojas", gestor: "gestor.paz", administrador: "admin",
  };
  return { usuario: usuarios[rol], nombre: ROLES.find((r) => r.id === rol)?.nombre ?? rol, rol };
}

/** `rutaInicial` activa un router en memoria (pruebas); sin ella se usa la URL del navegador.
 * `rolInicial` da por abierta la sesión de una cuenta de prueba de ese rol; `cuentaInicial` la fija tal cual. */
export function AppRouter({ rutaInicial, rolInicial, cuentaInicial }: { rutaInicial?: string; rolInicial?: RolId; cuentaInicial?: CuentaSesion }) {
  const contenido = (
    <SesionProvider cuentaInicial={cuentaInicial ?? (rolInicial ? cuentaDePrueba(rolInicial) : undefined)}>
      <RolProvider>
        <Rutas />
      </RolProvider>
    </SesionProvider>
  );
  if (rutaInicial) return <MemoryRouter initialEntries={[rutaInicial]}>{contenido}</MemoryRouter>;
  return <BrowserRouter>{contenido}</BrowserRouter>;
}
