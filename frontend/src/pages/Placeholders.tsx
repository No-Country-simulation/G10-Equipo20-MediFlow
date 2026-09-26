import { CheckCircle2, ChevronsUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { listarAlertas } from "../api";
import { etiquetaConcepto } from "../app/mensajes";
import { calcularPlazo } from "../app/plazos";
import { AccionAcuse } from "../components/AccionAcuse";
import { ChipPlazo } from "../components/Tags";
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

/**
 * Alertas críticas (RN-J7, RN-Q5). Las pendientes van de la más vencida a la más reciente;
 * las acusadas quedan al final como registro. Una alerta escalada se marca más fuerte, nunca más suave.
 */
export function AlertasPage() {
  const [alertas, setAlertas] = useState<AlertaListada[]>([]);
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [ahora, setAhora] = useState(() => new Date());

  const cargar = () => listarAlertas().then(setAlertas).catch(() => setAlertas([]));
  useEffect(() => {
    cargar();
    const reloj = setInterval(() => setAhora(new Date()), 15_000);
    return () => clearInterval(reloj);
  }, []);

  const ordenadas = useMemo(() => {
    const conPlazo = alertas.map((a) => ({ a, plazo: calcularPlazo(a.emitida_en, a.plazo_minutos, ahora) }));
    const pendientes = conPlazo.filter((x) => x.a.estado_acuse === "pendiente").sort((x, y) => x.plazo.minutosRestantes - y.plazo.minutosRestantes);
    const acusadas = conPlazo.filter((x) => x.a.estado_acuse !== "pendiente");
    return [...pendientes, ...acusadas];
  }, [alertas, ahora]);
  const escaladas = ordenadas.filter((x) => x.a.estado_acuse === "pendiente" && x.plazo.vencido).length;

  return (
    <>
      <Encabezado titulo="Alertas críticas" sub="La alerta persiste hasta que una persona identificada da el acuse. Nunca lleva datos del paciente. Las más vencidas van primero." />
      <div role="status" aria-live="polite">{mensaje && <p className="estado-carga ok-estado"><CheckCircle2 size={16} aria-hidden="true" />{mensaje}</p>}</div>
      {escaladas > 0 && (
        <p className="nota-escalada"><ChevronsUp size={16} aria-hidden="true" /><strong>{escaladas === 1 ? "1 alerta escalada" : `${escaladas} alertas escaladas`}</strong> al siguiente rol por falta de acuse en plazo.</p>
      )}
      <section className="tarjeta" style={{ padding: 0 }}>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Documento</th><th>Hallazgo</th><th>Emitida</th><th>Plazo</th><th>Estado</th><th><span className="oculto-visual">Acción</span></th></tr></thead>
            <tbody>
              {ordenadas.map(({ a, plazo }) => {
                const pendiente = a.estado_acuse === "pendiente";
                return (
                  <tr key={`${a.documento_id}-${a.version}`} className={`fila ${pendiente ? "critico" : "rutina"}`} data-testid="fila-alerta">
                    <td><Link to={`/documentos/${encodeURIComponent(a.documento_id)}`}><code>{a.documento_id}</code></Link><span className="secundaria">{a.canal} → {a.destinatario}</span></td>
                    <td>{a.concepto ? etiquetaConcepto(a.concepto) : <span className="muted">Sin concepto</span>}</td>
                    <td>{new Date(a.emitida_en).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" })}</td>
                    <td>{pendiente ? <ChipPlazo plazo={plazo} /> : <span className="muted">—</span>}</td>
                    <td>
                      {!pendiente ? <span className="tag exito"><CheckCircle2 size={13} aria-hidden="true" />Acusada · {a.acusado_por}</span>
                        : plazo.vencido ? <span className="tag critico fuerte"><ChevronsUp size={13} aria-hidden="true" />Escalada</span>
                        : <span className="tag critico">Pendiente</span>}
                    </td>
                    <td>{pendiente && <AccionAcuse documentoId={a.documento_id} onAcusado={(r) => { setMensaje(`Acuse de ${a.documento_id} registrado por ${r.acusado_por}. Circuito cerrado.`); cargar(); }} />}</td>
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
