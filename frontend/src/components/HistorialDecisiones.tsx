import type { DecisionRegistrada } from "../types";

/** RN-G2: qué regla se disparó, con qué evidencia, qué dijo el LLM y qué decidió la regla. */
export function HistorialDecisiones({ historial }: { historial: DecisionRegistrada[] }) {
  if (historial.length === 0) return <p className="muted">Sin decisiones registradas.</p>;
  return (
    <table className="tabla">
      <thead>
        <tr>
          <th>Regla</th>
          <th>Evidencia</th>
          <th>Propuesta LLM</th>
          <th>Decisión</th>
        </tr>
      </thead>
      <tbody>
        {historial.map((d, i) => (
          <tr key={i}>
            <td><code>{d.regla}</code></td>
            <td>{d.evidencia}</td>
            <td>{d.propuesta_llm ?? "—"}</td>
            <td>{d.decision}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
