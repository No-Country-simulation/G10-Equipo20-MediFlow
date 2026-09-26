import { ClipboardPen, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";

const TIPOS = ["Receta Médica", "Informe de Imágenes", "Informe de Laboratorio", "Orden de Procedimiento", "Epicrisis o Alta", "Certificado Médico", "No Clasificable"];
const DOCUMENTOS_PACIENTE = ["CC", "TI", "RC", "CE", "PA", "PT", "CN", "CD", "SC", "DE", "MS", "AS"];

interface Medicamento {
  dci: string; dosis: string; via: string; frecuencia: string; duracion: string; cantidad_numeros: string; cantidad_letras: string;
}
const MEDICAMENTO_VACIO: Medicamento = { dci: "", dosis: "", via: "", frecuencia: "", duracion: "", cantidad_numeros: "", cantidad_letras: "" };
const COLUMNAS_MEDICAMENTO: { clave: keyof Medicamento; etiqueta: string; ejemplo: string }[] = [
  { clave: "dci", etiqueta: "DCI", ejemplo: "losartan" },
  { clave: "dosis", etiqueta: "dosis", ejemplo: "50 mg" },
  { clave: "via", etiqueta: "vía", ejemplo: "oral" },
  { clave: "frecuencia", etiqueta: "frecuencia", ejemplo: "cada 24 h" },
  { clave: "duracion", etiqueta: "duración", ejemplo: "30 días" },
  { clave: "cantidad_numeros", etiqueta: "cantidad en números", ejemplo: "30" },
  { clave: "cantidad_letras", etiqueta: "cantidad en letras", ejemplo: "treinta" },
];
const SIGNOS: { clave: "FR" | "SpO2" | "FC" | "PAS" | "Temp"; etiqueta: string; decimal?: boolean }[] = [
  { clave: "FR", etiqueta: "FR" }, { clave: "SpO2", etiqueta: "SpO2" }, { clave: "FC", etiqueta: "FC" }, { clave: "PAS", etiqueta: "PAS" }, { clave: "Temp", etiqueta: "Temperatura", decimal: true },
];

type Texto = Record<string, string>;

function limpio(v: string): string | undefined {
  const t = v.trim();
  return t ? t : undefined;
}

/** Quita claves vacías para enviar solo lo que la persona transcribió. */
function compactar<T extends Record<string, unknown>>(o: T): Partial<T> {
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && !(typeof v === "object" && v !== null && !Array.isArray(v) && Object.keys(v).length === 0))) as Partial<T>;
}

/**
 * Transcripción de un documento que el motor de extracción no leyó (fallo técnico).
 * La persona copia los datos desde el original; al guardar, las reglas se aplican igual que sobre
 * una lectura del LLM: la prioridad solo puede subir y un hallazgo crítico del texto se mantiene.
 */
export function Transcripcion({ habilitado, enviando, onEnviar }: {
  habilitado: boolean;
  enviando: boolean;
  onEnviar: (transcripcion: Record<string, unknown>) => void;
}) {
  const [c, setC] = useState<Texto>({ tipo: "", prioridad: "Rutina", paciente_nombre: "", paciente_edad: "", doc_tipo: "", doc_valor: "", fecha: "",
    prof_nombre: "", prof_registro: "", dx_texto: "", dx_cie10: "", proc_texto: "", proc_cups: "", justificacion: "" });
  const [signos, setSignos] = useState<Texto>({ FR: "", SpO2: "", FC: "", PAS: "", Temp: "" });
  const [medicamentos, setMedicamentos] = useState<Medicamento[]>([{ ...MEDICAMENTO_VACIO }]);
  const [recetario, setRecetario] = useState(false);
  const campo = (clave: string) => ({ value: c[clave], onChange: (e: { target: { value: string } }) => setC({ ...c, [clave]: e.target.value }) });

  const esReceta = c.tipo === "Receta Médica";
  const esOrden = c.tipo === "Orden de Procedimiento";

  function construir(): Record<string, unknown> {
    const signosNum = Object.fromEntries(SIGNOS.flatMap(({ clave, decimal }) => {
      const t = signos[clave].trim().replace(",", ".");
      if (!t) return [];
      const n = decimal ? Number.parseFloat(t) : Number.parseInt(t, 10);
      return Number.isFinite(n) ? [[clave, n]] : [];
    }));
    const meds = esReceta
      ? medicamentos.filter((m) => m.dci.trim()).map((m) => compactar(Object.fromEntries(Object.entries(m).map(([k, v]) => [k, limpio(v)]))))
      : [];
    const edad = Number.parseInt(c.paciente_edad, 10);
    const extraccion = compactar({
      paciente: compactar({
        nombre: limpio(c.paciente_nombre),
        edad: Number.isFinite(edad) ? edad : undefined,
        documento: compactar({ tipo: limpio(c.doc_tipo), valor: limpio(c.doc_valor) }),
      }),
      profesional: compactar({ nombre: limpio(c.prof_nombre), registro_profesional: limpio(c.prof_registro) }),
      fecha_documento: limpio(c.fecha),
      signos_vitales: Object.keys(signosNum).length ? signosNum : undefined,
      diagnosticos: limpio(c.dx_texto) ? [compactar({ texto: c.dx_texto.trim(), cie10_sugerido: limpio(c.dx_cie10) })] : undefined,
      procedimientos: esOrden && limpio(c.proc_texto) ? [compactar({ texto: c.proc_texto.trim(), cups: limpio(c.proc_cups) })] : undefined,
      medicamentos: meds.length ? meds : undefined,
      justificacion_clinica: limpio(c.justificacion),
    });
    return {
      clasificacion: { tipo: c.tipo, nivel_prioridad_propuesto: c.prioridad },
      extraccion,
      ...(esReceta ? { condiciones: { recetario_oficial: recetario } } : {}),
    };
  }

  function enviar(e: FormEvent) {
    e.preventDefault();
    if (!c.tipo || !habilitado || enviando) return;
    onEnviar(construir());
  }

  return (
    <form className="transcripcion" data-testid="transcripcion" onSubmit={enviar} aria-labelledby="t-titulo">
      <p className="muted">El motor no leyó este documento. Copia los datos desde el original; al guardar, las reglas se aplican igual que sobre una lectura automática. La prioridad solo puede subir: un hallazgo crítico del texto se mantiene.</p>

      <fieldset>
        <legend>Documento</legend>
        <div className="formulario">
          <label>Tipo de documento
            <select required {...campo("tipo")}>
              <option value="">Elige el tipo…</option>
              {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label>Prioridad que indica el documento
            <select {...campo("prioridad")}>
              <option value="Rutina">Rutina</option>
              <option value="Urgente">Urgente</option>
              <option value="Crítico">Crítico</option>
            </select>
          </label>
          <label>Fecha del documento<input {...campo("fecha")} placeholder="dd/mm/aaaa" inputMode="numeric" /></label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Paciente</legend>
        <div className="formulario">
          <label>Nombre del paciente<input {...campo("paciente_nombre")} autoComplete="off" /></label>
          <label>Edad<input {...campo("paciente_edad")} inputMode="numeric" /></label>
          <label>Tipo de documento del paciente
            <select {...campo("doc_tipo")}>
              <option value="">Sin indicar</option>
              {DOCUMENTOS_PACIENTE.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label>Número de documento del paciente<input {...campo("doc_valor")} inputMode="numeric" autoComplete="off" /></label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Profesional y diagnóstico</legend>
        <div className="formulario">
          <label>Nombre del profesional<input {...campo("prof_nombre")} autoComplete="off" /></label>
          <label>Registro del profesional<input {...campo("prof_registro")} placeholder="RM 45678" /></label>
          <label>Diagnóstico principal<input {...campo("dx_texto")} /></label>
          <label>Código CIE-10<input {...campo("dx_cie10")} placeholder="I10" /></label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Signos vitales <span className="muted">(si el documento los trae; NEWS2 lo calcula el sistema)</span></legend>
        <div className="formulario signos">
          {SIGNOS.map(({ clave, etiqueta }) => (
            <label key={clave}>{etiqueta}<input value={signos[clave]} onChange={(e) => setSignos({ ...signos, [clave]: e.target.value })} inputMode="decimal" /></label>
          ))}
        </div>
      </fieldset>

      {esReceta && (
        <fieldset>
          <legend>Medicamentos</legend>
          {medicamentos.map((m, i) => (
            <div key={i} className="fila-medicamento">
              {COLUMNAS_MEDICAMENTO.map(({ clave, etiqueta, ejemplo }) => (
                <input key={clave} aria-label={`Medicamento ${i + 1}: ${etiqueta}`} placeholder={`${etiqueta} (${ejemplo})`} value={m[clave]}
                  onChange={(e) => setMedicamentos(medicamentos.map((x, j) => (j === i ? { ...x, [clave]: e.target.value } : x)))} />
              ))}
              {medicamentos.length > 1 && (
                <button type="button" className="secundario icono" aria-label={`Quitar medicamento ${i + 1}`} onClick={() => setMedicamentos(medicamentos.filter((_, j) => j !== i))}><Trash2 size={16} aria-hidden="true" /></button>
              )}
            </div>
          ))}
          <div className="acciones">
            <button type="button" className="secundario" onClick={() => setMedicamentos([...medicamentos, { ...MEDICAMENTO_VACIO }])}><Plus size={16} aria-hidden="true" />Agregar medicamento</button>
            <label className="interruptor"><input type="checkbox" checked={recetario} onChange={(e) => setRecetario(e.target.checked)} />Viene en recetario oficial</label>
          </div>
        </fieldset>
      )}

      {esOrden && (
        <fieldset>
          <legend>Procedimiento</legend>
          <div className="formulario">
            <label>Procedimiento<input {...campo("proc_texto")} /></label>
            <label>CUPS<input {...campo("proc_cups")} inputMode="numeric" /></label>
            <label className="ancho">Justificación clínica<textarea rows={2} {...campo("justificacion")} /></label>
          </div>
        </fieldset>
      )}

      <div className="acciones">
        <button type="submit" disabled={!c.tipo || !habilitado || enviando}><ClipboardPen size={16} aria-hidden="true" />{enviando ? "Aplicando reglas…" : "Guardar transcripción y aplicar reglas"}</button>
        {!c.tipo && <span className="muted">Elige el tipo de documento para continuar.</span>}
        {c.tipo && !habilitado && <span className="muted">Escribe tu usuario en «Firmo como» para guardar.</span>}
      </div>
    </form>
  );
}
