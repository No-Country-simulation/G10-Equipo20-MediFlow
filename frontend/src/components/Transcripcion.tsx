import { ClipboardPen, Eraser, Plus, Trash2 } from "lucide-react";
import { useEffect, useId, useMemo, useState, type FormEvent, type InputHTMLAttributes } from "react";

import { etiquetaTipo } from "../app/mensajes";
import type { NivelPrioridad } from "../types";

const TIPOS = ["Receta Médica", "Informe de Imágenes", "Informe de Laboratorio", "Orden de Procedimiento", "Epicrisis o Alta", "Certificado Médico", "No Clasificable"];
const DOCUMENTOS_PACIENTE = ["CC", "TI", "RC", "CE", "PA", "PT", "CN", "CD", "SC", "DE", "MS", "AS"];

interface Medicamento {
  dci: string; dosis: string; via: string; frecuencia: string; duracion: string; cantidad_numeros: string; cantidad_letras: string;
}
const MEDICAMENTO_VACIO: Medicamento = { dci: "", dosis: "", via: "", frecuencia: "", duracion: "", cantidad_numeros: "", cantidad_letras: "" };
const COLUMNAS_MEDICAMENTO: { clave: keyof Medicamento; etiqueta: string; cabecera: string }[] = [
  { clave: "dci", etiqueta: "DCI", cabecera: "DCI" },
  { clave: "dosis", etiqueta: "dosis", cabecera: "Dosis" },
  { clave: "via", etiqueta: "vía", cabecera: "Vía" },
  { clave: "frecuencia", etiqueta: "frecuencia", cabecera: "Frecuencia" },
  { clave: "duracion", etiqueta: "duración", cabecera: "Duración" },
  { clave: "cantidad_numeros", etiqueta: "cantidad en números", cabecera: "Cantidad (n.º)" },
  { clave: "cantidad_letras", etiqueta: "cantidad en letras", cabecera: "Cantidad (letras)" },
];
const SIGNOS: { clave: "FR" | "SpO2" | "FC" | "PAS" | "Temp"; etiqueta: string; decimal?: boolean }[] = [
  { clave: "FR", etiqueta: "FR" }, { clave: "SpO2", etiqueta: "SpO2" }, { clave: "FC", etiqueta: "FC" }, { clave: "PAS", etiqueta: "PAS" }, { clave: "Temp", etiqueta: "Temperatura", decimal: true },
];

type Texto = Record<string, string>;

const CAMPOS_INICIALES: Texto = { tipo: "", prioridad: "Rutina", paciente_nombre: "", paciente_edad: "", doc_tipo: "", doc_valor: "", fecha: "",
  prof_nombre: "", prof_registro: "", dx_texto: "", dx_cie10: "", proc_texto: "", proc_cups: "", justificacion: "" };
const SIGNOS_INICIALES: Texto = { FR: "", SpO2: "", FC: "", PAS: "", Temp: "" };

/**
 * Campo con su ejemplo debajo, nunca dentro: un ejemplo dentro del campo se lee como un dato ya escrito.
 * El ejemplo queda asociado al campo para el lector de pantalla.
 */
function Campo({ etiqueta, ejemplo, ...props }: { etiqueta: string; ejemplo?: string } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <div className="campo-t">
      <label>{etiqueta}<input {...props} aria-describedby={ejemplo ? `${id}-ej` : undefined} /></label>
      {ejemplo && <span id={`${id}-ej`} className="pista">{ejemplo}</span>}
    </div>
  );
}

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
export function Transcripcion({ habilitado, enviando, onEnviar, onCambio, prioridadActual, discreto = false }: {
  habilitado: boolean;
  enviando: boolean;
  onEnviar: (transcripcion: Record<string, unknown>) => void;
  /** Avisa si hay datos escritos sin guardar, para no cambiar de documento con ellos (paciente equivocado). */
  onCambio?: (sucio: boolean) => void;
  /** La prioridad arranca en la actual del documento: nunca se muestra Rutina en un caso ya Crítico. */
  prioridadActual?: NivelPrioridad | null;
  /** Modo discreto: lo que se escribe del paciente no se lee en una pantalla compartida. */
  discreto?: boolean;
}) {
  const iniciales = useMemo<Texto>(() => ({ ...CAMPOS_INICIALES, prioridad: prioridadActual ?? "Rutina" }), [prioridadActual]);
  const [c, setC] = useState<Texto>(iniciales);
  const [signos, setSignos] = useState<Texto>(SIGNOS_INICIALES);
  const [medicamentos, setMedicamentos] = useState<Medicamento[]>([{ ...MEDICAMENTO_VACIO }]);
  const [recetario, setRecetario] = useState(false);
  const sucio = Object.entries(c).some(([k, v]) => v !== iniciales[k]) || Object.values(signos).some((v) => v.trim() !== "")
    || medicamentos.some((m) => Object.values(m).some((v) => v.trim() !== "")) || recetario;
  useEffect(() => { onCambio?.(sucio); }, [sucio, onCambio]);

  function descartar() {
    setC(iniciales);
    setSignos(SIGNOS_INICIALES);
    setMedicamentos([{ ...MEDICAMENTO_VACIO }]);
    setRecetario(false);
  }
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
              {TIPOS.map((t) => <option key={t} value={t}>{etiquetaTipo(t)}</option>)}
            </select>
          </label>
          <div className="campo-t">
            <label>Prioridad que indica el documento
              <select {...campo("prioridad")} aria-describedby="t-prioridad-ayuda">
                <option value="Rutina">Rutina</option>
                <option value="Urgente">Urgente</option>
                <option value="Crítico">Crítico</option>
              </select>
            </label>
            <span id="t-prioridad-ayuda" className="pista">{prioridadActual ? `Actual: ${prioridadActual}. Las reglas pueden subirla; desde aquí no se baja.` : "Las reglas pueden subirla; desde aquí no se baja."}</span>
          </div>
          <Campo etiqueta="Fecha del documento" ejemplo="Formato dd/mm/aaaa" {...campo("fecha")} inputMode="numeric" />
        </div>
      </fieldset>

      <fieldset>
        <legend>Paciente</legend>
        <div className="formulario">
          <label>Nombre del paciente<input {...campo("paciente_nombre")} autoComplete="off" className={discreto ? "enmascarado" : undefined} /></label>
          <label>Edad<input {...campo("paciente_edad")} inputMode="numeric" /></label>
          <label>Tipo de documento del paciente
            <select {...campo("doc_tipo")}>
              <option value="">Sin indicar</option>
              {DOCUMENTOS_PACIENTE.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label>Número de documento del paciente<input {...campo("doc_valor")} inputMode="numeric" autoComplete="off" className={discreto ? "enmascarado" : undefined} /></label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Profesional y diagnóstico</legend>
        <div className="formulario">
          <label>Nombre del profesional<input {...campo("prof_nombre")} autoComplete="off" /></label>
          <Campo etiqueta="Registro del profesional" ejemplo="Ej.: RM 45678" {...campo("prof_registro")} />
          <label>Diagnóstico principal<input {...campo("dx_texto")} /></label>
          <Campo etiqueta="Código CIE-10" ejemplo="Ej.: I10" {...campo("dx_cie10")} />
        </div>
      </fieldset>

      <fieldset>
        <legend>Signos vitales</legend>
        <p className="pista" style={{ marginTop: 0 }}>Solo si el documento los trae. El NEWS2 lo calcula el sistema.</p>
        <div className="formulario signos">
          {SIGNOS.map(({ clave, etiqueta }) => (
            <label key={clave}>{etiqueta}<input value={signos[clave]} onChange={(e) => setSignos({ ...signos, [clave]: e.target.value })} inputMode="decimal" /></label>
          ))}
        </div>
      </fieldset>

      {esReceta && (
        <fieldset>
          <legend>Medicamentos</legend>
          <div className="fila-medicamento cabecera" data-testid="cabecera-medicamentos" aria-hidden="true">
            {COLUMNAS_MEDICAMENTO.map(({ clave, cabecera }) => <span key={clave}>{cabecera}</span>)}
          </div>
          {medicamentos.map((m, i) => (
            <div key={i} className="fila-medicamento">
              {COLUMNAS_MEDICAMENTO.map(({ clave, etiqueta }) => (
                <input key={clave} aria-label={`Medicamento ${i + 1}: ${etiqueta}`} value={m[clave]}
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
        {sucio && <button type="button" className="secundario" onClick={descartar}><Eraser size={16} aria-hidden="true" />Descartar transcripción</button>}
        {!c.tipo && <span className="muted">Elige el tipo de documento para continuar.</span>}
      </div>
    </form>
  );
}
