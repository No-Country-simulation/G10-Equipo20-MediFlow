import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { acusarAlerta, consultarDocumento, ErrorApi, listarAlertas } from "../api";
import { calcularPlazo } from "../app/plazos";
import { CockpitScreen } from "../components/screens/CockpitScreen";
import { ProcesamientoScreen } from "../components/screens/ProcesamientoScreen";
import { RevisionHumanaScreen } from "../components/screens/RevisionHumanaScreen";
import { EntregaScreen } from "../components/screens/EntregaScreen";
import type { AlertaListada, DocumentoDetalle } from "../types";

function Encabezado({ titulo, sub }: { titulo: string; sub: string }) {
  return (
    <header className="encabezado">
      <div>
        <h1>{titulo}</h1>
        <p className="sub">{sub}</p>
      </div>
    </header>
  );
}

function Pendiente({ titulo, sub, fase }: { titulo: string; sub: string; fase: string }) {
  return (
    <>
      <Encabezado titulo={titulo} sub={sub} />
      <section className="tarjeta">
        <p className="muted">Esta sección se construye en la {fase} del plan de diseño. La API necesaria se describe en el estudio UX/UI.</p>
      </section>
    </>
  );
}

/** Detalle provisional (fase A): reutiliza el cockpit hasta que llegue el banco de trabajo de tres paneles (fase B). */
export function DetalleDocumentoPage() {
  const { id = "" } = useParams();
  const [detalle, setDetalle] = useState<DocumentoDetalle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pestana, setPestana] = useState<"cockpit" | "procesamiento" | "entrega">("cockpit");

  useEffect(() => {
    consultarDocumento(id).then(setDetalle).catch((e) => setError(e instanceof ErrorApi ? e.detalle : "No hay conexión con la API."));
  }, [id]);

  return (
    <>
      <header className="encabezado">
        <div>
          <p className="muted"><Link to="/documentos">Documentos</Link> / <code>{id}</code></p>
          <h1>Detalle del documento</h1>
        </div>
        <div className="acciones">
          <button type="button" className={pestana === "cockpit" ? "" : "secundario"} onClick={() => setPestana("cockpit")}>Cockpit</button>
          <button type="button" className={pestana === "procesamiento" ? "" : "secundario"} onClick={() => setPestana("procesamiento")}>Ciclo de vida</button>
          <button type="button" className={pestana === "entrega" ? "" : "secundario"} onClick={() => setPestana("entrega")}>Entregas</button>
        </div>
      </header>
      {error && <p className="error">{error}</p>}
      {detalle && pestana === "cockpit" && <CockpitScreen detalle={detalle} onContinuar={() => setPestana("entrega")} />}
      {detalle && pestana === "procesamiento" && <ProcesamientoScreen detalle={detalle} onContinuar={() => setPestana("cockpit")} />}
      {detalle && pestana === "entrega" && <EntregaScreen detalle={detalle} onReiniciar={() => setPestana("cockpit")} />}
    </>
  );
}

export function RevisionPage() {
  return (
    <>
      <Encabezado titulo="Cola de revisión" sub="Ordenada por prioridad clínica y antigüedad (RN-J1). Plazos: Crítico 15 min, Urgente 2 h, Rutina 24 h hábiles (RN-J2)." />
      <RevisionHumanaScreen documentoInicial={null} onResuelto={() => window.location.assign("/revision")} />
    </>
  );
}

export function AlertasPage() {
  const [alertas, setAlertas] = useState<AlertaListada[]>([]);
  const [usuario, setUsuario] = useState("");
  const [mensaje, setMensaje] = useState<string | null>(null);

  const cargar = () => listarAlertas().then(setAlertas).catch(() => setAlertas([]));
  useEffect(() => { cargar(); }, []);

  async function acusar(documentoId: string) {
    try {
      const r = await acusarAlerta(documentoId, usuario.trim());
      setMensaje(`Acuse de ${documentoId} registrado por ${r.acusado_por}.`);
      cargar();
    } catch (e) {
      setMensaje(e instanceof ErrorApi ? e.detalle : "No hay conexión con la API.");
    }
  }

  return (
    <>
      <Encabezado titulo="Alertas críticas" sub="Circuito cerrado: la alerta persiste hasta el acuse de un usuario identificado (RN-J7, RN-Q5). Sin datos del paciente (RN-Q4)." />
      <section className="tarjeta" style={{ marginBottom: 12 }}>
        <label style={{ maxWidth: 320 }}>
          Usuario que da el acuse
          <input value={usuario} onChange={(e) => setUsuario(e.target.value)} placeholder="jefe.urgencias" />
        </label>
        {mensaje && <p className="muted" role="status">{mensaje}</p>}
      </section>
      <section className="tarjeta" style={{ padding: 0 }}>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Documento</th><th>Concepto</th><th>Emitida</th><th>Plazo</th><th>Estado</th><th></th></tr></thead>
            <tbody>
              {alertas.map((a) => {
                const plazo = calcularPlazo(a.emitida_en, a.plazo_minutos);
                return (
                  <tr key={`${a.documento_id}-${a.version}`} className="fila critico" data-testid="fila-alerta">
                    <td><Link to={`/documentos/${encodeURIComponent(a.documento_id)}`}><code>{a.documento_id}</code></Link><span className="secundaria">{a.canal} → {a.destinatario}</span></td>
                    <td>{a.concepto ?? "—"}</td>
                    <td>{new Date(a.emitida_en).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" })}</td>
                    <td>{a.estado_acuse === "pendiente" ? <span className={`plazo ${plazo.vencido ? "vencido" : plazo.apremia ? "apremia" : ""}`}>{plazo.texto}</span> : <span className="muted">—</span>}</td>
                    <td>{a.estado_acuse === "acusado" ? <span className="tag exito">Acusada · {a.acusado_por}</span> : plazo.vencido ? <span className="tag urgente">Escalada</span> : <span className="tag critico">Pendiente</span>}</td>
                    <td>{a.estado_acuse === "pendiente" && <button type="button" className="peligro" disabled={!usuario.trim()} onClick={() => acusar(a.documento_id)}>Dar acuse</button>}</td>
                  </tr>
                );
              })}
              {alertas.length === 0 && <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 24 }}>No hay alertas críticas.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

export function FarmaciaPage() {
  return <Pendiente titulo="Farmacia" sub="Recetas por verificar, con doble verificación en alto riesgo y control especial (RN-E6, RN-J6, RN-CO9)." fase="fase C" />;
}
export function AutorizacionesPage() {
  return <Pendiente titulo="Autorizaciones" sub="Órdenes ambulatorias con su documentación mínima (RN-E5). Las de urgencias no esperan aquí (RN-CO13)." fase="fase C" />;
}
export function EntregasPage() {
  return <Pendiente titulo="Entregas" sub="Confirmación de destinos y entregas retenidas (RN-A4, RN-J7)." fase="fase C" />;
}
export function ConfiguracionPage() {
  return <Pendiente titulo="Configuración" sub="Umbrales dentro de rango, destinos, plazos y modo simulación (RN-L1, RN-L6)." fase="fase D" />;
}
export function MetricasPage() {
  return <Pendiente titulo="Métricas" sub="Indicadores calculados del historial (RN-R1)." fase="fase D" />;
}
export function AdministracionPage() {
  return <Pendiente titulo="Administración" sub="Usuarios, roles y pack de país. Nada clínico (RN-K2)." fase="fase D" />;
}
