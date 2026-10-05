import type { DecisionRegistrada } from "../types";

/** RN-G2: qué regla se disparó, con qué evidencia, qué dijo el LLM y qué decidió la regla. Lista compacta: cabe en un panel angosto. */
export function HistorialDecisiones({ historial }: { historial: DecisionRegistrada[] }) {
  if (historial.length === 0) return <p className="muted">Sin decisiones registradas.</p>;
  return (
    <ol className="decisiones">
      {historial.map((d, i) => (
        <li key={i}>
          <div className="fila-decision">
            <code>{d.regla}</code>
            <strong>{d.decision}</strong>
          </div>
          <p className="evidencia">{d.evidencia}</p>
          {d.propuesta_llm && <p className="secundaria">Propuesta del LLM: {d.propuesta_llm}</p>}
        </li>
      ))}
    </ol>
  );
}
