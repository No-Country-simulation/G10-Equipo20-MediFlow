import { BellRing, CheckCircle2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { acusarAlerta, ErrorApi, listarAlertas } from "../api";
import { calcularPlazo } from "../app/plazos";
import { useUsuario } from "../app/usuario";
import { Vacio } from "../components/Vacio";
import type { AlertaListada } from "../types";

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

export function AlertasPage() {
  const [alertas, setAlertas] = useState<AlertaListada[]>([]);
  const [usuario] = useUsuario();
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
      <Encabezado titulo="Alertas críticas" sub="La alerta persiste hasta que una persona identificada da el acuse. Nunca lleva datos del paciente." />
      {mensaje && <p className="estado-carga" role="status">{mensaje}</p>}
      <section className="tarjeta" style={{ padding: 0 }}>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Documento</th><th>Concepto</th><th>Emitida</th><th>Plazo</th><th>Estado</th><th></th></tr></thead>
            <tbody>
              {alertas.map((a) => {
                const plazo = calcularPlazo(a.emitida_en, a.plazo_minutos);
                return (
                  <tr key={`${a.documento_id}-${a.version}`} className="fila critico" data-testid="fila-alerta">
                    <td><Link to={`/documentos/${encodeURIComponent(a.documento_id)}`}><code>{a.documento_id}</code></Link><span className="secundaria">{a.canal} → {a.destinatario} · <Link to={`/documentos/${encodeURIComponent(a.documento_id)}`}>Abrir ›</Link></span></td>
                    <td>{a.concepto ?? "—"}</td>
                    <td>{new Date(a.emitida_en).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" })}</td>
                    <td>{a.estado_acuse === "pendiente" ? <span className={`plazo ${plazo.vencido ? "vencido" : plazo.apremia ? "apremia" : ""}`}>{plazo.texto}</span> : <span className="muted">—</span>}</td>
                    <td>{a.estado_acuse === "acusado" ? <span className="tag exito">Acusada · {a.acusado_por}</span> : plazo.vencido ? <span className="tag urgente">Escalada</span> : <span className="tag critico">Pendiente</span>}</td>
                    <td>{a.estado_acuse === "pendiente" && <button type="button" disabled={!usuario.trim()} onClick={() => acusar(a.documento_id)}><BellRing size={16} aria-hidden="true" />Dar acuse</button>}</td>
                  </tr>
                );
              })}
              {alertas.length === 0 && <tr><td colSpan={6}><Vacio icono={CheckCircle2} titulo="No hay alertas críticas" texto="Cuando un documento resulte Crítico aparecerá aquí hasta que alguien dé el acuse." /></td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
