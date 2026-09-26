import { BrowserRouter, MemoryRouter, Navigate, Route, Routes } from "react-router-dom";

import App from "../App";
import { AppShell } from "../components/shell/AppShell";
import { DocumentosPage } from "../pages/DocumentosPage";
import {
  AdministracionPage,
  AlertasPage,
  AutorizacionesPage,
  ConfiguracionPage,
  DetalleDocumentoPage,
  EntregasPage,
  FarmaciaPage,
  MetricasPage,
  RevisionPage,
} from "../pages/Placeholders";
import { RolProvider } from "./RolContext";
import type { RolId } from "./roles";

function Rutas() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/documentos" replace />} />
        <Route path="/documentos" element={<DocumentosPage />} />
        <Route path="/documentos/:id" element={<DetalleDocumentoPage />} />
        <Route path="/revision" element={<RevisionPage />} />
        <Route path="/alertas" element={<AlertasPage />} />
        <Route path="/farmacia" element={<FarmaciaPage />} />
        <Route path="/autorizaciones" element={<AutorizacionesPage />} />
        <Route path="/entregas" element={<EntregasPage />} />
        <Route path="/configuracion" element={<ConfiguracionPage />} />
        <Route path="/metricas" element={<MetricasPage />} />
        <Route path="/administracion" element={<AdministracionPage />} />
        <Route path="*" element={<Navigate to="/documentos" replace />} />
      </Route>
      <Route path="/demo" element={<App />} />
    </Routes>
  );
}

/** `rutaInicial` activa un router en memoria (tests); sin ella se usa la URL del navegador. */
export function AppRouter({ rutaInicial, rolInicial }: { rutaInicial?: string; rolInicial?: RolId }) {
  const contenido = (
    <RolProvider rolInicial={rolInicial}>
      <Rutas />
    </RolProvider>
  );
  if (rutaInicial) return <MemoryRouter initialEntries={[rutaInicial]}>{contenido}</MemoryRouter>;
  return <BrowserRouter>{contenido}</BrowserRouter>;
}
