import { BrowserRouter, MemoryRouter, Navigate, Route, Routes } from "react-router-dom";

import App from "../App";
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
import type { RolId } from "./roles";
import { SesionProvider, useSesion } from "./sesion";
import { UsuarioProvider } from "./usuario";

function Rutas() {
  const { cuenta, exigida, sinCuentas } = useSesion();
  // Instalación sin cuentas (RN-S3) o con sesión obligatoria (RN-K5): sin sesión no se muestra nada más que el ingreso.
  if ((exigida || sinCuentas) && !cuenta) return <IngresarPage />;
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
      <Route path="/demo" element={<App />} />
      <Route path="/ingresar" element={<IngresarPage />} />
    </Routes>
  );
}

/** `rutaInicial` activa un router en memoria (tests); sin ella se usa la URL del navegador. */
export function AppRouter({ rutaInicial, rolInicial }: { rutaInicial?: string; rolInicial?: RolId }) {
  const contenido = (
    <SesionProvider>
      <RolProvider rolInicial={rolInicial}>
        <UsuarioProvider>
          <Rutas />
        </UsuarioProvider>
      </RolProvider>
    </SesionProvider>
  );
  if (rutaInicial) return <MemoryRouter initialEntries={[rutaInicial]}>{contenido}</MemoryRouter>;
  return <BrowserRouter>{contenido}</BrowserRouter>;
}
