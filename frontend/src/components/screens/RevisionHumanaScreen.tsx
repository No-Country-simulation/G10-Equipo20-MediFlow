import { useEffect, useState } from "react";

import { colaRevision, ErrorApi, resolverRevision } from "../../api";
import type { AccionRevision, ItemCola, ResultadoTriaje } from "../../types";
import { PrioridadBadge } from "../PrioridadBadge";

interface Props {
  documentoInicial: string | null;
  onResuelto: (documentoId: string, estado: string, resultado: ResultadoTriaje) => void;
}

const ROLES = ["auditor_clinico", "quimico_farmaceutico", "auditor_autorizaciones", "jefe_urgencias"];

export function formatearPlazo(minutos: number): string {
  return minutos < 60 ? `${minutos} min` : `${Math.round(minutos / 60)} h`;
}

/** Pantalla 5: cola y acciones de revisión humana (RN-J1 a RN-J8). */
export function RevisionHumanaScreen({ documentoInicial, onResuelto }: Props) {
  const [cola, setCola] = useState<ItemCola[]>([]);
  const [seleccionado, setSeleccionado] = useState<string | null>(documentoInicial);
  const [usuario, setUsuario] = useState("");
  const [rol, setRol] = useState(ROLES[0]);
  const [motivo, setMotivo] = useState("");
  const [correcciones, setCorrecciones] = useState('{\n  "clasificacion.score_confianza": 0.95\n}');
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    colaRevision().then(setCola).catch((e) => setError(String(e)));
  }, []);

  const correccionesValidas = (() => {
    try {
      const v = JSON.parse(correcciones);
      return v && typeof v === "object" && Object.keys(v).length > 0;
    } catch {
      return false;
    }
  })();

  async function resolver(accion: AccionRevision) {
    if (!seleccionado) return;
    setEnviando(true);
    setError(null);
    try {
      const r = await resolverRevision(seleccionado, {
        accion,
        usuario: usuario.trim(),
        rol,
        motivo,
        correcciones: accion === "corregir" ? JSON.parse(correcciones) : null,
      });
      onResuelto(r.documento_id, r.estado, r.resultado);
    } catch (e) {
      setError(e instanceof ErrorApi ? `${e.status}: ${e.detalle}` : String(e));
    } finally {
      setEnviando(false);
    }
  }

  const tieneUsuario = usuario.trim() !== "";

  return (
    <section className="pantalla">
      <h2>5. Revisión humana</h2>
      <p className="muted">Ordenada por prioridad clínica y luego por antigüedad (RN-J1). Plazos: Crítico 15 min, Urgente 2 h, Rutina 24 h hábiles (RN-J2).</p>

      <ul className="cola">
        {cola.map((item) => (
          <li
            key={item.documento_id}
            data-testid="item-cola"
            className={item.documento_id === seleccionado ? "seleccionado" : ""}
            onClick={() => setSeleccionado(item.documento_id)}
          >
            <PrioridadBadge nivel={item.nivel_prioridad} />
            <code>{item.documento_id}</code> · {item.tipo ?? "sin tipo"} · <em>{item.motivo_auditoria}</em>
            <span className="muted"> · plazo {formatearPlazo(item.plazo_minutos)}</span>
            {item.campos_dudosos.length > 0 && <div className="muted">Dudosos: {item.campos_dudosos.join(", ")}</div>}
          </li>
        ))}
        {cola.length === 0 && <li className="muted">La cola está vacía.</li>}
      </ul>

      {seleccionado && (
        <div className="tarjeta">
          <h3>Resolver <code>{seleccionado}</code></h3>
          <div className="grid-2">
            <label>
              Usuario
              <input value={usuario} onChange={(e) => setUsuario(e.target.value)} placeholder="ana.auditora" />
            </label>
            <label>
              Rol
              <select value={rol} onChange={(e) => setRol(e.target.value)}>
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </label>
          </div>
          <label>
            Motivo (obligatorio para rechazar y para bajar prioridad, RN-J5)
            <input value={motivo} onChange={(e) => setMotivo(e.target.value)} />
          </label>
          <label>
            Correcciones (JSON por ruta de campo; "nivel_prioridad" para cambiar el nivel)
            <textarea rows={4} value={correcciones} onChange={(e) => setCorrecciones(e.target.value)} />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <div className="acciones">
            <button type="button" disabled={!tieneUsuario || enviando} onClick={() => resolver("aprobar")}>Aprobar</button>
            <button type="button" className="secundario" disabled={!tieneUsuario || !correccionesValidas || enviando} onClick={() => resolver("corregir")}>
              Corregir y re-evaluar
            </button>
            <button type="button" className="peligro" disabled={!tieneUsuario || motivo.trim() === "" || enviando} onClick={() => resolver("rechazar")}>
              Rechazar
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
