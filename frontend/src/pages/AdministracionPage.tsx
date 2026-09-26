import { useEffect, useState } from "react";

import { cambiarEstadoUsuario, crearUsuario, ErrorApi, listarAccesos, listarUsuarios, obtenerPack, puestaEnMarcha } from "../api";
import { ROLES } from "../app/roles";
import { useUsuario } from "../app/usuario";
import type { Acceso, FichaPack, PuestaEnMarcha, UsuarioAdmin } from "../types";

const FORMULARIO_VACIO = { usuario: "", nombre: "", rol: "auditor_clinico", tipo: "persona" };

function nombreRol(id: string): string {
  return ROLES.find((r) => r.id === id)?.nombre ?? id;
}

/** Administración del sistema: usuarios y pack de país. Nada clínico (RN-K2). */
export function AdministracionPage() {
  const [actor] = useUsuario();
  const [usuarios, setUsuarios] = useState<UsuarioAdmin[] | null>(null);
  const [puesta, setPuesta] = useState<PuestaEnMarcha | null>(null);
  const [pack, setPack] = useState<FichaPack | null>(null);
  const [accesos, setAccesos] = useState<Acceso[]>([]);
  const [filtroDoc, setFiltroDoc] = useState("");
  const [form, setForm] = useState(FORMULARIO_VACIO);
  const [mensaje, setMensaje] = useState<string | null>(null);

  const cargar = () => {
    listarUsuarios().then(setUsuarios).catch(() => setUsuarios([]));
    puestaEnMarcha().then(setPuesta).catch(() => setPuesta(null));
    obtenerPack().then(setPack).catch(() => setPack(null));
  };
  useEffect(() => { cargar(); }, []);
  useEffect(() => {
    let activo = true;
    listarAccesos(filtroDoc.trim() || undefined).then((a) => activo && setAccesos(a)).catch(() => activo && setAccesos([]));
    return () => { activo = false; };
  }, [filtroDoc]);

  function informar(e: unknown) {
    setMensaje(e instanceof ErrorApi ? `${e.status}: ${e.detalle}` : "No hay conexión con la API.");
  }

  async function crear() {
    setMensaje(null);
    try {
      const u = await crearUsuario({ ...form, usuario: form.usuario.trim(), nombre: form.nombre.trim(), actor: actor.trim() });
      setMensaje(`Usuario ${u.usuario} creado como ${nombreRol(u.rol)}.`);
      setForm(FORMULARIO_VACIO);
      cargar();
    } catch (e) {
      informar(e);
    }
  }

  async function cambiarEstado(u: UsuarioAdmin) {
    setMensaje(null);
    try {
      const r = await cambiarEstadoUsuario(u.usuario, !u.activo, actor.trim());
      setMensaje(r.activo ? `${r.usuario} reactivado.` : `${r.usuario} desactivado: pierde acceso de inmediato; su historial permanece.`);
      cargar();
    } catch (e) {
      informar(e);
    }
  }

  const yo = actor.trim();
  const cumplidos = puesta?.requisitos.filter((r) => r.cumplido).length ?? 0;

  return (
    <>
      <header className="encabezado">
        <div>
          <h1>Administración</h1>
          <p className="sub">Usuarios, accesos y pack de país. Quien administra no ve datos clínicos; aquí solo hay identificadores de documento.</p>
        </div>
      </header>
      {mensaje && <p className="estado-carga" role="status">{mensaje}</p>}

      <div className="dos-columnas">
        <section className="tarjeta" data-testid="puesta-en-marcha">
          <h2>Puesta en marcha</h2>
          <p className="muted">{puesta ? `${cumplidos} de ${puesta.requisitos.length} requisitos cumplidos${puesta.listo ? ". La instalación puede activarse." : ". Aún no se activa."}` : "—"}</p>
          <ul className="lista-check">
            {puesta?.requisitos.map((r) => (
              <li key={r.clave}>
                <span className={`marca ${r.cumplido ? "" : "no"}`} aria-label={r.cumplido ? "cumplido" : "pendiente"}>{r.cumplido ? "✓" : "✗"}</span>
                <span>{r.requisito}<span className="secundaria">{r.detalle}</span></span>
              </li>
            ))}
          </ul>
        </section>

        <section className="tarjeta" data-testid="pack">
          <h2>Pack de país</h2>
          {pack ? (
            <>
              <p><strong>{pack.nombre} ({pack.pais})</strong> · versión {pack.version_pack}</p>
              <ul className="accesos">
                <li>Registro profesional: <strong>{pack.identidad_profesional.registro}</strong> ({pack.identidad_profesional.ambito})</li>
                <li>Diagnósticos: {pack.terminologia.diagnosticos} · procedimientos: {pack.terminologia.procedimientos} · medicamentos: {pack.terminologia.medicamentos}</li>
                <li>Fechas {pack.formato.formato_fecha} · decimal "{pack.formato.separador_decimal}" · miles "{pack.formato.separador_miles}"</li>
                <li>Retención: <strong>{pack.retencion.anios} años</strong> ({pack.retencion.archivo_gestion_anios} gestión + {pack.retencion.archivo_central_anios} central) · purga automática: {pack.retencion.purga_automatica ? "sí" : "nunca"}</li>
                <li>Listas: {pack.listas.hallazgos_criticos} hallazgos críticos · {pack.listas.alto_riesgo} alto riesgo · {pack.listas.control_especial} control especial</li>
                <li>Tipos de documento: {Object.entries(pack.tipos_documento_paciente).map(([k, v]) => `${k} (${v.estado.replace(/_/g, " ")})`).join(", ")}</li>
                {pack.por_confirmar.length > 0 && <li><span className="tag urgente">por confirmar</span> {pack.por_confirmar.join(", ")} · no activan decisiones automáticas</li>}
              </ul>
            </>
          ) : <p className="muted">—</p>}
        </section>
      </div>

      <section className="tarjeta" style={{ marginTop: 12 }}>
        <h2>Usuarios</h2>
        <p className="muted">Un usuario desactivado pierde acceso de inmediato y conserva su historial. Las cuentas de servicio no firman acciones clínicas.</p>
        <div className="formulario" style={{ marginBottom: 10 }}>
          <label>Nombre de usuario<input value={form.usuario} onChange={(e) => setForm({ ...form, usuario: e.target.value })} placeholder="jefe.rojas" /></label>
          <label>Nombre completo<input value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} placeholder="Andrés Rojas" /></label>
          <label>Rol del usuario
            <select value={form.rol} onChange={(e) => setForm({ ...form, rol: e.target.value })}>
              {ROLES.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
            </select>
          </label>
          <label>Tipo de cuenta
            <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })}>
              <option value="persona">Persona</option>
              <option value="servicio">Servicio (integración)</option>
            </select>
          </label>
          <button type="button" disabled={!yo || !form.usuario.trim() || !form.nombre.trim()} onClick={crear}>Crear usuario</button>
        </div>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Usuario</th><th>Rol</th><th>Tipo</th><th>Estado</th><th></th></tr></thead>
            <tbody>
              {usuarios?.map((u) => (
                <tr key={u.usuario} data-testid="fila-usuario" className={`fila ${u.activo ? "rutina" : "critico"}`}>
                  <td><code>{u.usuario}</code><span className="secundaria">{u.nombre}</span></td>
                  <td>{nombreRol(u.rol)}</td>
                  <td>{u.tipo === "servicio" ? <span className="tag urgente">Servicio</span> : "Persona"}</td>
                  <td>{u.activo ? <span className="tag exito">Activo</span> : <span className="tag critico">Inactivo</span>}<span className="secundaria">{u.desactivado_en ? `desde ${new Date(u.desactivado_en).toLocaleString("es-CO")}` : `alta por ${u.creado_por}`}</span></td>
                  <td><button type="button" className={u.activo ? "peligro" : "secundario"} disabled={!yo} onClick={() => cambiarEstado(u)}>{u.activo ? "Desactivar" : "Activar"}</button></td>
                </tr>
              ))}
              {usuarios && usuarios.length === 0 && <tr><td colSpan={5} className="muted" style={{ textAlign: "center", padding: 20 }}>Sin usuarios registrados. Mientras tanto cualquiera firma con su nombre (MVP sin autenticación).</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="tarjeta" style={{ marginTop: 12 }} data-testid="accesos">
        <div className="encabezado" style={{ marginBottom: 6 }}>
          <h2>Accesos a documentos</h2>
          <label style={{ minWidth: 220 }}>
            Filtrar por documento
            <input value={filtroDoc} onChange={(e) => setFiltroDoc(e.target.value)} placeholder="DOC-2026-001" />
          </label>
        </div>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Cuándo</th><th>Quién</th><th>Qué vio</th><th>Documento</th></tr></thead>
            <tbody>
              {accesos.map((a, i) => (
                <tr key={`${a.documento_id}-${a.fecha_hora}-${i}`} className="fila rutina">
                  <td>{new Date(a.fecha_hora).toLocaleString("es-CO")}</td><td>{a.usuario}</td><td>{a.accion.replace(/_/g, " ")}</td><td><code>{a.documento_id}</code></td>
                </tr>
              ))}
              {accesos.length === 0 && <tr><td colSpan={4} className="muted" style={{ textAlign: "center", padding: 20 }}>Sin accesos registrados.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
