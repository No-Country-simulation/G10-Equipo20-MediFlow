import { CheckCircle2, ChevronsUp, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { listarAlertas } from "../api";
import { etiquetaConcepto } from "../app/mensajes";
import { usePared } from "../app/pared";
import { calcularPlazo } from "../app/plazos";
import { AccionAcuse } from "../components/AccionAcuse";
import { ChipPlazo } from "../components/Tags";
import { Vacio } from "../components/Vacio";
import type { AlertaListada } from "../types";

/** Cada cuánto se vuelve a pedir la lista. Una alerta crítica nueva no puede esperar a que alguien recargue. */
const REFRESCO_MS = 15_000;

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

const clave = (a: AlertaListada) => `${a.documento_id}-${a.version}`;
const hora = (d: Date) => d.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/** Hora de emisión; si no es de hoy, con la fecha, para no confundir una alerta de ayer con una de esta mañana. */
function emitida(iso: string, ahora: Date): string {
  const d = new Date(iso);
  const horaCorta = d.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === ahora.toDateString() ? `hoy ${horaCorta}` : `${d.toLocaleDateString("es-CO", { day: "2-digit", month: "2-digit" })} ${horaCorta}`;
}

/**
 * Alertas críticas (RN-J7, RN-Q5). Es la pantalla inicial del jefe de urgencias: se actualiza sola, dice cuándo
 * se actualizó, avisa si quedó desactualizada y marca lo que llegó mientras estaba abierta. Las pendientes van
 * de la más vencida a la más reciente; una alerta escalada se marca más fuerte, nunca más suave.
 */
export function AlertasPage() {
  const { activo: pared } = usePared();
  const [alertas, setAlertas] = useState<AlertaListada[]>([]);
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [ahora, setAhora] = useState(() => new Date());
  const [actualizado, setActualizado] = useState<Date | null>(null);
  const [fallo, setFallo] = useState<Date | null>(null);
  const [nuevas, setNuevas] = useState<Set<string>>(() => new Set());
  const conocidas = useRef<Set<string> | null>(null);

  const cargar = useCallback(() => listarAlertas()
    .then((lista) => {
      const ids = new Set(lista.map(clave));
      const previas = conocidas.current;
      if (previas) {
        const llegadas = [...ids].filter((id) => !previas.has(id));
        if (llegadas.length) setNuevas((actuales) => new Set([...actuales, ...llegadas]));
      }
      conocidas.current = ids;
      setAlertas(lista);
      setActualizado(new Date());
      setFallo(null);
    })
    .catch(() => setFallo(new Date())), []);

  useEffect(() => {
    cargar();
    const refresco = setInterval(cargar, REFRESCO_MS);
    const reloj = setInterval(() => setAhora(new Date()), REFRESCO_MS);
    return () => { clearInterval(refresco); clearInterval(reloj); };
  }, [cargar]);

  const ordenadas = useMemo(() => {
    const conPlazo = alertas.map((a) => ({ a, plazo: calcularPlazo(a.emitida_en, a.plazo_minutos, ahora) }));
    const pendientes = conPlazo.filter((x) => x.a.estado_acuse === "pendiente").sort((x, y) => x.plazo.minutosRestantes - y.plazo.minutosRestantes);
    const acusadas = conPlazo.filter((x) => x.a.estado_acuse !== "pendiente");
    return [...pendientes, ...acusadas];
  }, [alertas, ahora]);
  const pendientes = ordenadas.filter((x) => x.a.estado_acuse === "pendiente").length;
  const escaladas = ordenadas.filter((x) => x.a.estado_acuse === "pendiente" && x.plazo.vencido).length;
  const masAntigua = ordenadas.find((x) => x.a.estado_acuse === "pendiente");

  // La cuenta en la pestaña: se ve aunque la pantalla muestre otra cosa.
  useEffect(() => {
    const anterior = document.title;
    document.title = pendientes > 0 ? `(${pendientes}) Alertas críticas · MediFlow` : "Alertas críticas · MediFlow";
    return () => { document.title = anterior; };
  }, [pendientes]);

  return (
    <>
      <Encabezado titulo="Alertas críticas" sub="La alerta persiste hasta que una persona identificada da el acuse. Nunca lleva datos del paciente. Las más vencidas van primero." />
      {pared && (
        <section className={`resumen-pared ${pendientes === 0 ? "en-calma" : ""}`} data-testid="resumen-pared" aria-label="Resumen de alertas">
          <span className="cuenta">{pendientes}</span>
          <div>
            <strong>{pendientes === 0 ? "Ninguna alerta sin acuse" : `${pendientes} sin acuse`}</strong>
            {masAntigua && <span>la más antigua: {etiquetaConcepto(masAntigua.a.concepto) || "sin concepto"}, {masAntigua.plazo.texto}</span>}
          </div>
        </section>
      )}
      <div className="barra-estado">
        <p className="muted" data-testid="actualizado">
          <RefreshCw size={14} aria-hidden="true" />
          {actualizado ? <>Actualizado a las {hora(actualizado)} · se actualiza sola cada {REFRESCO_MS / 1000} s</> : "Cargando alertas…"}
        </p>
        {escaladas > 0 && (
          <p className="nota-escalada"><ChevronsUp size={16} aria-hidden="true" /><strong>{escaladas === 1 ? "1 alerta escalada" : `${escaladas} alertas escaladas`}</strong> al siguiente rol por falta de acuse en plazo.</p>
        )}
      </div>
      {fallo && (
        <p className="estado-carga error" role="alert">
          No se pudo actualizar a las {hora(fallo)}. La lista puede estar desactualizada{actualizado ? ` desde las ${hora(actualizado)}` : ""}; se reintenta sola cada {REFRESCO_MS / 1000} s.
        </p>
      )}
      <div role="status" aria-live="polite">{mensaje && <p className="estado-carga ok-estado"><CheckCircle2 size={16} aria-hidden="true" />{mensaje}</p>}</div>
      <section className="tarjeta" style={{ padding: 0 }}>
        <div className="scroll">
          <table className="tabla-densa tabla-alertas">
            <thead><tr><th>{pared ? "Hallazgo" : "Documento"}</th><th>{pared ? "Documento" : "Hallazgo"}</th><th>Emitida</th><th>Plazo</th><th>Estado</th><th><span className="oculto-visual">Acción</span></th></tr></thead>
            <tbody>
              {ordenadas.map(({ a, plazo }) => {
                const pendiente = a.estado_acuse === "pendiente";
                const esNueva = pendiente && nuevas.has(clave(a));
                return (
                  <tr key={clave(a)} className={`fila ${pendiente ? "critico" : "rutina"}${esNueva ? " nueva" : ""}`} data-testid="fila-alerta">
                    {pared && <td className="hallazgo">{a.concepto ? etiquetaConcepto(a.concepto) : <span className="muted">Sin concepto</span>}{esNueva && <span className="tag nueva">Nueva</span>}</td>}
                    <td>
                      <Link to={`/documentos/${encodeURIComponent(a.documento_id)}`}><code>{a.documento_id}</code></Link>
                      {!pared && esNueva && <span className="tag nueva">Nueva</span>}
                      <span className="secundaria">{a.canal} → {a.destinatario}</span>
                    </td>
                    {!pared && <td>{a.concepto ? etiquetaConcepto(a.concepto) : <span className="muted">Sin concepto</span>}</td>}
                    <td>{emitida(a.emitida_en, ahora)}</td>
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
              {alertas.length === 0 && !fallo && <tr><td colSpan={6}><Vacio icono={CheckCircle2} titulo="No hay alertas críticas" texto="Cuando un documento resulte Crítico aparecerá aquí hasta que alguien dé el acuse." /></td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
