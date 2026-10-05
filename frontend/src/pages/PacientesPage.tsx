import { Contact } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listarPacientes } from "../api";
import { useRol } from "../app/RolContext";
import { enmascarar } from "../app/usuario";
import { EstadoMensaje, type Mensaje } from "../components/EstadoMensaje";
import { Vacio } from "../components/Vacio";
import type { ListadoPacientes } from "../types";

const LIMITE = 20;

/** Directorio de pacientes (RN-M6): todo lo asociado a una persona, a partir de los documentos ya enrutados. */
export function PacientesPage() {
  const { modoDiscreto } = useRol();
  const [listado, setListado] = useState<ListadoPacientes | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [mensaje, setMensaje] = useState<Mensaje | null>(null);

  useEffect(() => {
    let activo = true;
    listarPacientes({ q, limit: LIMITE, offset })
      .then((l) => { if (activo) { setListado(l); setMensaje(null); } })
      .catch(() => activo && setMensaje({ texto: "No hay conexión con el servidor. El directorio se mostrará cuando vuelva.", error: true }));
    return () => { activo = false; };
  }, [q, offset]);

  const total = listado?.total ?? 0;
  const desde = total === 0 ? 0 : offset + 1;
  const hasta = Math.min(offset + LIMITE, total);
  const ver = (valor: string) => (modoDiscreto ? enmascarar(valor) : valor);

  return (
    <>
      <header className="encabezado">
        <div>
          <h1>Pacientes</h1>
          <p className="sub">
            Cada documento enrutado con una identificación válida queda en la ficha de su paciente.
            Si un documento de identidad ya está registrado con otro nombre, el documento clínico no se vincula solo: pasa a revisión humana.
          </p>
        </div>
      </header>
      <EstadoMensaje mensaje={mensaje} />

      <section className="tarjeta" style={{ padding: 0 }}>
        <div style={{ padding: "12px 16px 0" }}>
          <h2>Directorio <span className="muted" style={{ fontWeight: 400 }}>· {total} paciente{total === 1 ? "" : "s"}</span></h2>
          <div className="filtros">
            <label>
              Buscar
              <input type="search" value={busqueda} onChange={(e) => setBusqueda(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { setOffset(0); setQ(busqueda.trim()); } }}
                placeholder="Nombre o número de documento" />
            </label>
          </div>
        </div>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Paciente</th><th>Identificación</th><th>Edad</th><th>Documentos</th><th></th></tr></thead>
            <tbody>
              {listado?.items.map((p) => (
                <tr key={p.id} data-testid="fila-paciente" className="fila rutina">
                  <td>{ver(p.nombre)}</td>
                  <td><code>{p.tipo_documento} {ver(p.numero_documento)}</code></td>
                  <td>{p.edad != null ? `${p.edad} años` : <span className="muted">sin dato</span>}</td>
                  <td>{p.documentos}</td>
                  <td><Link to={`/pacientes/${p.id}`} aria-label={`Abrir la ficha del paciente ${p.id}`}>Abrir ›</Link></td>
                </tr>
              ))}
              {listado && listado.items.length === 0 && (
                <tr><td colSpan={5}>
                  <Vacio icono={Contact} titulo={q ? "Ningún paciente coincide con la búsqueda" : "Todavía no hay pacientes"}
                    texto={q ? "Prueba con otro nombre o con el número de documento completo." : "Aparecerán aquí cuando se enrute el primer documento con identificación válida."} />
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="paginacion" style={{ padding: "10px 16px" }}>
          <span>Mostrando {desde}–{hasta} de {total}</span>
          <span className="acciones">
            <button type="button" className="secundario" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMITE))}>Anterior</button>
            <button type="button" className="secundario" disabled={hasta >= total} onClick={() => setOffset(offset + LIMITE)}>Siguiente</button>
          </span>
        </div>
      </section>
    </>
  );
}
