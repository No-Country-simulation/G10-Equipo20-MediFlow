import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import type { Medicamento } from "../types";

/** Los campos de un medicamento tal como los lee el LLM (RN-CO8). `dosis` es la concentración por unidad, como en el documento. */
const CAMPOS: { clave: keyof ValoresMedicamento; etiqueta: string; pista?: string }[] = [
  { clave: "dci", etiqueta: "Medicamento (DCI)", pista: "principio activo, en minúsculas" },
  { clave: "dosis", etiqueta: "Concentración o dosis", pista: "tal como aparece: 500 mg, 0,5 mg, 5.000 UI" },
  { clave: "unidades_por_toma", etiqueta: "Unidades por toma", pista: "2 tabletas, 1 tableta con alimentos, 10 ml" },
  { clave: "forma_farmaceutica", etiqueta: "Forma farmacéutica" },
  { clave: "via", etiqueta: "Vía" },
  { clave: "frecuencia", etiqueta: "Frecuencia" },
  { clave: "duracion", etiqueta: "Duración" },
  { clave: "cantidad_numeros", etiqueta: "Cantidad total (números)" },
  { clave: "cantidad_letras", etiqueta: "Cantidad total (letras)" },
];

type ValoresMedicamento = Record<"dci" | "dosis" | "unidades_por_toma" | "forma_farmaceutica" | "via" | "frecuencia" | "duracion" | "cantidad_numeros" | "cantidad_letras", string>;

interface Fila {
  original: ValoresMedicamento | null;  // null: lo agregó la persona
  valores: ValoresMedicamento;
  quitado: boolean;
}

function vacio(): ValoresMedicamento {
  return { dci: "", dosis: "", unidades_por_toma: "", forma_farmaceutica: "", via: "", frecuencia: "", duracion: "", cantidad_numeros: "", cantidad_letras: "" };
}

function desde(m: Medicamento): ValoresMedicamento {
  const v = vacio();
  for (const { clave } of CAMPOS) v[clave] = (m[clave] ?? "") as string;
  return v;
}

function comoPropuesta(v: ValoresMedicamento): Record<string, string | null> {
  return Object.fromEntries(CAMPOS.map(({ clave }) => [clave, v[clave].trim() || null]));
}

/**
 * Corrección de los medicamentos leídos (RN-J4, RN-J8): cada campo cambiado viaja como su propia corrección, con el
 * valor leído y el corregido. Agregar uno que el LLM no leyó o quitar uno que inventó reemplaza la lista completa.
 */
export function EditorMedicamentos({ medicamentos, enviando, onAplicar, onCancelar }: {
  medicamentos: Medicamento[]; enviando: boolean; onAplicar: (correcciones: Record<string, unknown>) => void; onCancelar: () => void;
}) {
  const [filas, setFilas] = useState<Fila[]>(() => medicamentos.map((m) => ({ original: desde(m), valores: desde(m), quitado: false })));
  const [activo, setActivo] = useState(0);

  const fila = filas[activo];
  const estructuraCambio = filas.some((f) => f.quitado || f.original === null);
  const correcciones: Record<string, unknown> = {};
  if (estructuraCambio) {
    correcciones["extraccion.medicamentos"] = filas.filter((f) => !f.quitado).map((f) => comoPropuesta(f.valores));
  } else {
    filas.forEach((f, i) => {
      for (const { clave } of CAMPOS) {
        if (f.valores[clave].trim() !== (f.original?.[clave] ?? "").trim()) correcciones[`extraccion.medicamentos[${i}].${clave}`] = f.valores[clave].trim() || null;
      }
    });
  }
  const nCambios = Object.keys(correcciones).length;
  const sinDci = filas.some((f) => !f.quitado && !f.valores.dci.trim());

  function cambiar(clave: keyof ValoresMedicamento, valor: string) {
    setFilas(filas.map((f, i) => (i === activo ? { ...f, valores: { ...f.valores, [clave]: valor } } : f)));
  }

  function agregar() {
    setFilas([...filas, { original: null, valores: vacio(), quitado: false }]);
    setActivo(filas.length);
  }

  function quitar() {
    if (fila.original === null) {
      const restantes = filas.filter((_, i) => i !== activo);
      setFilas(restantes);
      setActivo(Math.max(0, Math.min(activo, restantes.length - 1)));
    } else {
      setFilas(filas.map((f, i) => (i === activo ? { ...f, quitado: !f.quitado } : f)));
    }
  }

  return (
    <div className="tarjeta correccion" data-testid="editor-medicamentos">
      <div className="acciones" style={{ alignItems: "flex-end", flexWrap: "wrap" }}>
        <label style={{ flex: 1, minWidth: 220 }}>
          Medicamento a corregir
          <select value={activo} onChange={(e) => setActivo(Number(e.target.value))} disabled={filas.length === 0}>
            {filas.map((f, i) => <option key={i} value={i}>{i + 1}. {f.valores.dci.trim() || "(nuevo)"}{f.quitado ? " · se quita" : ""}{f.original === null ? " · agregado" : ""}</option>)}
          </select>
        </label>
        <button type="button" className="secundario" onClick={agregar}><Plus size={16} aria-hidden="true" />Agregar medicamento</button>
        {fila && <button type="button" className="secundario" onClick={quitar}><Trash2 size={16} aria-hidden="true" />{fila.quitado ? "No quitarlo" : "Quitar este medicamento"}</button>}
      </div>
      {fila && !fila.quitado && (
        <div className="campos" style={{ marginTop: 10 }}>
          {CAMPOS.map(({ clave, etiqueta, pista }) => (
            <label key={clave} className={fila.original && fila.valores[clave].trim() !== (fila.original[clave] ?? "").trim() ? "cambiado" : ""}>
              {etiqueta}
              <input value={fila.valores[clave]} placeholder={pista} onChange={(e) => cambiar(clave, e.target.value)} />
              {fila.original && fila.original[clave] && fila.valores[clave].trim() !== fila.original[clave].trim() && <span className="secundaria">leído: {fila.original[clave]}</span>}
            </label>
          ))}
        </div>
      )}
      {fila?.quitado && <p className="aviso" style={{ marginTop: 8 }}>Este medicamento se quitará de la lectura al aplicar la corrección.</p>}
      <div className="acciones" style={{ marginTop: 12 }}>
        <button type="button" disabled={nCambios === 0 || sinDci || enviando} onClick={() => onAplicar(correcciones)}>Aplicar corrección</button>
        <button type="button" className="secundario" onClick={onCancelar}>Cancelar</button>
        <span className="muted pista">{sinDci ? "Cada medicamento necesita su DCI." : nCambios === 0 ? "Cambia algún campo, agrega o quita un medicamento." : estructuraCambio ? "Se reemplaza la lista completa de medicamentos." : `${nCambios} campo${nCambios === 1 ? "" : "s"} corregido${nCambios === 1 ? "" : "s"}.`}</span>
      </div>
      <p className="muted">Lo que corriges queda verificado: las reglas se vuelven a aplicar sin llamar al LLM y el caso no vuelve a la cola por ese campo.</p>
    </div>
  );
}
