import { FileText, History, Pencil } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { editarPaciente, ErrorApi, obtenerPaciente } from "../api";
import { etiquetaTipo } from "../app/mensajes";
import { useRol } from "../app/RolContext";
import { enmascarar, useUsuario } from "../app/usuario";
import { EstadoMensaje, textoDeError, type Mensaje } from "../components/EstadoMensaje";
import { TagEstado, TagPrioridad } from "../components/Tags";
import { Vacio } from "../components/Vacio";
import type { PacienteDetalle } from "../types";

const ETIQUETA_CAMPO: Record<string, string> = { nombre: "Nombre", edad: "Edad", sexo: "Sexo" };

function fecha(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" }) : "—";
}

/** Ficha de un paciente (RN-M6): sus documentos y las correcciones a sus datos, cada una con su rastro (RN-G4). */
export function PacienteDetallePage() {
  const { id } = useParams();
  const { rol, modoDiscreto } = useRol();
  const [usuario] = useUsuario();
  const [paciente, setPaciente] = useState<PacienteDetalle | null>(null);
  const [noExiste, setNoExiste] = useState(false);
  const [editando, setEditando] = useState(false);
  const [nombre, setNombre] = useState("");
  const [edad, setEdad] = useState("");
  const [motivo, setMotivo] = useState("");
  const [mensaje, setMensaje] = useState<Mensaje | null>(null);

  useEffect(() => {
    let activo = true;
    obtenerPaciente(Number(id))
      .then((p) => activo && setPaciente(p))
      .catch((e) => {
        if (!activo) return;
        if (e instanceof ErrorApi && e.status === 404) setNoExiste(true);
        else setMensaje({ texto: textoDeError(e), error: true });
      });
    return () => { activo = false; };
  }, [id]);

  if (noExiste) {
    return (
      <section className="tarjeta" style={{ marginTop: 16 }}>
        <h1>Paciente no encontrado</h1>
        <p><Link to="/pacientes">‹ Volver al directorio</Link></p>
      </section>
    );
  }

  const ver = (valor: string | null | undefined) => (modoDiscreto ? enmascarar(valor) : valor ?? "—");
  const yo = usuario.trim();
  const edadNueva = edad.trim() === "" ? null : Number(edad);
  const cambios: { nombre?: string; edad?: number | null } = {};
  if (paciente && nombre.trim() !== paciente.nombre) cambios.nombre = nombre.trim();
  if (paciente && edadNueva !== paciente.edad) cambios.edad = edadNueva;
  const edadValida = edadNueva === null || (Number.isInteger(edadNueva) && edadNueva >= 0 && edadNueva <= 130);
  const listo = Object.keys(cambios).length > 0 && nombre.trim() !== "" && edadValida && motivo.trim() !== "" && yo !== "";

  function abrirEdicion() {
    if (!paciente) return;
    setNombre(paciente.nombre);
    setEdad(paciente.edad != null ? String(paciente.edad) : "");
    setMotivo("");
    setMensaje(null);
    setEditando(true);
  }

  async function guardar() {
    if (!paciente) return;
    try {
      const actualizado = await editarPaciente(paciente.id, { ...cambios, motivo: motivo.trim() });
      setPaciente({ ...paciente, ...actualizado });
      setEditando(false);
      setMensaje({ texto: "Datos corregidos. El cambio quedó en el historial de la ficha." });
    } catch (e) {
      setMensaje({ texto: textoDeError(e), error: true });
    }
  }

  return (
    <>
      <header className="encabezado">
        <div>
          <p style={{ margin: 0 }}><Link to="/pacientes">‹ Pacientes</Link></p>
          <h1>{paciente ? ver(paciente.nombre) : "Paciente"}</h1>
          {paciente && (
            <p className="sub">
              <code>{paciente.tipo_documento} {ver(paciente.numero_documento)}</code> · {paciente.edad != null ? `${paciente.edad} años` : "edad sin dato"}
              {paciente.sexo ? ` · ${paciente.sexo}` : ""} · en el directorio desde {fecha(paciente.creado_en)}
            </p>
          )}
        </div>
        {paciente && !editando && rol.id === "auditor_clinico" && (
          <button type="button" className="secundario" onClick={abrirEdicion}><Pencil size={16} aria-hidden="true" />Corregir datos</button>
        )}
      </header>
      <EstadoMensaje mensaje={mensaje} />

      {paciente && editando && (
        <section className="tarjeta" data-testid="edicion-paciente">
          <h2>Corregir datos del paciente</h2>
          <p className="muted">
            Para un dato mal registrado, por ejemplo un apellido con error que genera conflictos de identidad.
            El número de documento no se edita: otro número es otra persona.
          </p>
          <div className="campos" style={{ marginTop: 8 }}>
            <label className="ancho">Nombre<input value={nombre} onChange={(e) => setNombre(e.target.value)} /></label>
            <label>Edad<input type="number" min={0} max={130} value={edad} onChange={(e) => setEdad(e.target.value)} /></label>
            <label>Motivo de la corrección<input value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Obligatorio" /></label>
          </div>
          <div className="acciones" style={{ marginTop: 12 }}>
            <button type="button" disabled={!listo} onClick={guardar} aria-describedby="falta-edicion">Guardar corrección</button>
            <button type="button" className="secundario" onClick={() => setEditando(false)}>Cancelar</button>
            {!listo && (
              <span id="falta-edicion" className="muted pista">
                {!yo ? "Escribe tu usuario en la barra lateral." : Object.keys(cambios).length === 0 ? "Cambia el nombre o la edad." : !edadValida ? "La edad va de 0 a 130." : "Falta el motivo."}
              </span>
            )}
          </div>
        </section>
      )}

      <section className="tarjeta" style={{ marginTop: 12, padding: 0 }}>
        <div style={{ padding: "12px 16px 0" }}>
          <h2>Documentos <span className="muted" style={{ fontWeight: 400 }}>· {paciente?.documentos_listado.length ?? 0}</span></h2>
        </div>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Documento</th><th>Tipo</th><th>Prioridad</th><th>Estado</th><th></th></tr></thead>
            <tbody>
              {paciente?.documentos_listado.map((d) => (
                <tr key={`${d.documento_id}-${d.version}`} data-testid="documento-de-paciente" className="fila rutina">
                  <td><code>{d.documento_id}</code><span className="secundaria">{d.fecha_documento ?? fecha(d.creado_en)}{d.version > 1 ? ` · versión ${d.version}` : ""}</span></td>
                  <td>{etiquetaTipo(d.tipo) || <span className="muted">—</span>}</td>
                  <td><TagPrioridad nivel={d.nivel_prioridad} /></td>
                  <td><TagEstado estado={d.estado} /></td>
                  <td><Link to={`/documentos/${encodeURIComponent(d.documento_id)}`}>Abrir ›</Link></td>
                </tr>
              ))}
              {paciente && paciente.documentos_listado.length === 0 && (
                <tr><td colSpan={5}><Vacio icono={FileText} titulo="Sin documentos vinculados" /></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="tarjeta" style={{ marginTop: 12 }} data-testid="historial-paciente">
        <h2>Correcciones a la ficha</h2>
        {paciente && paciente.historial.length === 0 && <Vacio icono={History} titulo="Sin correcciones" texto="Los datos vienen tal como llegaron en el primer documento." />}
        <ul className="accesos">
          {paciente?.historial.map((h) => (
            <li key={h.fecha_hora}>
              <strong>{h.usuario}</strong> · {fecha(h.fecha_hora)} · {h.motivo}
              <span className="secundaria">
                {Object.keys(h.nuevo).map((campo) => `${ETIQUETA_CAMPO[campo] ?? campo}: ${ver(String(h.anterior[campo] ?? "sin dato"))} → ${ver(String(h.nuevo[campo] ?? "sin dato"))}`).join(" · ")}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
