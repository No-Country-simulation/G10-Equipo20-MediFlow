import { useState } from "react";

import { enviarDocumento, ErrorApi } from "../../api";
import { CASOS } from "../../data/casos";
import type { CanalOrigen, Cobertura, DocumentoDetalle } from "../../types";

const CANALES: CanalOrigen[] = ["Guardia_Emergencias", "Consulta_Ambulatoria", "Hospitalizado", "Externo"];
const COBERTURAS: Cobertura[] = ["contributivo", "subsidiado", "especial_excepcion", "soat", "arl", "plan_voluntario", "no_afiliado"];

interface Props {
  onEnviado: (detalle: DocumentoDetalle) => void;
}

/** Pantalla 1: ingesta (RN-A1, RN-A2, RN-A3, RN-A9, RN-A10). */
export function IngestaScreen({ onEnviado }: Props) {
  const [documentoId, setDocumentoId] = useState("");
  const [canal, setCanal] = useState<CanalOrigen>("Consulta_Ambulatoria");
  const [cobertura, setCobertura] = useState<Cobertura | "">("");
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const listo = documentoId.trim() !== "" && texto.trim() !== "" && !enviando;

  function cargarCaso(id: string) {
    const caso = CASOS.find((c) => c.id === id);
    if (!caso) return;
    setDocumentoId(caso.documento_id);
    setCanal(caso.canal_origen);
    setCobertura(caso.cobertura_paciente ?? "");
    setTexto(caso.texto);
    setError(null);
  }

  async function enviar() {
    setEnviando(true);
    setError(null);
    try {
      const detalle = await enviarDocumento({
        documento_id: documentoId.trim(),
        canal_origen: canal,
        cobertura_paciente: cobertura || null,
        tipo_contenido: "texto",
        contenido_texto: texto,
      });
      if (detalle.codigo_error) {
        setError(`Documento rechazado: ${detalle.codigo_error}`);
        return;
      }
      onEnviado(detalle);
    } catch (e) {
      setError(e instanceof ErrorApi ? `${e.status}: ${e.detalle}` : String(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section className="pantalla">
      <h2>1. Ingesta</h2>
      <p className="muted">Texto clínico sintético. Antes de salir hacia el LLM se seudonimiza en el backend (RN-M1).</p>

      <div className="casos">
        {CASOS.map((c) => (
          <button key={c.id} type="button" className="secundario" title={c.descripcion} onClick={() => cargarCaso(c.id)}>
            {c.nombre}
          </button>
        ))}
      </div>

      <div className="grid-2">
        <label>
          documento_id
          <input value={documentoId} onChange={(e) => setDocumentoId(e.target.value)} placeholder="DOC-CLIN-2026-8942" />
        </label>
        <label>
          Canal de origen
          <select value={canal} onChange={(e) => setCanal(e.target.value as CanalOrigen)}>
            {CANALES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label>
          Cobertura del paciente (opcional)
          <select value={cobertura} onChange={(e) => setCobertura(e.target.value as Cobertura | "")}>
            <option value="">no informada</option>
            {COBERTURAS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      </div>

      <label>
        Texto del documento
        <textarea rows={14} value={texto} onChange={(e) => setTexto(e.target.value)} />
      </label>

      {error && <p className="error" role="alert">{error}</p>}

      <button type="button" disabled={!listo} onClick={enviar}>
        {enviando ? "Procesando…" : "Enviar al agente"}
      </button>
    </section>
  );
}
