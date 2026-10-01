import { BrowserRouter, MemoryRouter, Navigate, Route, Routes } from "react-router-dom";

import App from "../App";
import { AppShell } from "../components/shell/AppShell";
import { AdministracionPage } from "../pages/AdministracionPage";
import { AutorizacionesPage } from "../pages/AutorizacionesPage";
import { ConfiguracionPage } from "../pages/ConfiguracionPage";
import { DetalleDocumentoPage } from "../pages/DetalleDocumentoPage";
import { DocumentosPage } from "../pages/DocumentosPage";
import { EntregasPage } from "../pages/EntregasPage";
import { FarmaciaPage } from "../pages/FarmaciaPage";
import { InicioPage } from "../pages/InicioPage";
import { MetricasPage } from "../pages/MetricasPage";
import { PacienteDetallePage } from "../pages/PacienteDetallePage";
import { PacientesPage } from "../pages/PacientesPage";
import { AlertasPage } from "../pages/Placeholders";
import { RevisionPage } from "../pages/RevisionPage";
import { RolProvider } from "./RolContext";
import type { RolId } from "./roles";
import { UsuarioProvider } from "./usuario";

function Rutas() {
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
      <Route path="/demo" element={<App />} />
    </Routes>
  );
}

/** `rutaInicial` activa un router en memoria (tests); sin ella se usa la URL del navegador. */
export function AppRouter({ rutaInicial, rolInicial }: { rutaInicial?: string; rolInicial?: RolId }) {
  const contenido = (
    <RolProvider rolInicial={rolInicial}>
      <UsuarioProvider>
        <Rutas />
      </UsuarioProvider>
    </RolProvider>
  );
  if (rutaInicial) return <MemoryRouter initialEntries={[rutaInicial]}>{contenido}</MemoryRouter>;
  return <BrowserRouter>{contenido}</BrowserRouter>;
}
