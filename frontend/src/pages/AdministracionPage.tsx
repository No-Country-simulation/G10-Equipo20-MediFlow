import { useEffect, useState } from "react";

import { anotarConsultaRegistro, cambiarEstadoProfesional, cambiarEstadoUsuario, crearProfesional, crearUsuario, definirClave, listarAccesos, listarProfesionales, listarUsuarios, obtenerPack, puestaEnMarcha } from "../api";
import { EstadoMensaje, textoDeError, type Mensaje } from "../components/EstadoMensaje";
import { ROLES } from "../app/roles";
import { useUsuario } from "../app/usuario";
import type { Acceso, FichaPack, ProfesionalRegistrado, PuestaEnMarcha, UsuarioAdmin } from "../types";

const FORMULARIO_VACIO = { usuario: "", nombre: "", rol: "auditor_clinico", tipo: "persona" };
const PROFESIONAL_VACIO = { registro: "", nombre: "", profesion: "", tipo_documento: "CC", numero_documento: "" };
const CLAVE_MINIMA = 8;

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
  const [claveInicial, setClaveInicial] = useState("");
  const [cambioDeClave, setCambioDeClave] = useState<{ usuario: string; clave: string } | null>(null);
  const [mensaje, setMensaje] = useState<Mensaje | null>(null);
  const [profesionales, setProfesionales] = useState<ProfesionalRegistrado[] | null>(null);
  const [profesional, setProfesional] = useState(PROFESIONAL_VACIO);

  const cargar = () => {
    listarUsuarios().then(setUsuarios).catch(() => setUsuarios([]));
    listarProfesionales().then(setProfesionales).catch(() => setProfesionales([]));
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
    setMensaje({ texto: textoDeError(e), error: true });
  }

  async function crear() {
    setMensaje(null);
    try {
      const u = await crearUsuario({ ...form, usuario: form.usuario.trim(), nombre: form.nombre.trim(), ...(claveInicial ? { clave: claveInicial } : {}) });
      setMensaje({ texto: `Usuario ${u.usuario} creado como ${nombreRol(u.rol)}${claveInicial ? ", con clave para iniciar sesión" : ""}.` });
      setForm(FORMULARIO_VACIO);
      setClaveInicial("");
      cargar();
    } catch (e) {
      informar(e);
    }
  }

  async function crearEnPadron() {
    setMensaje(null);
    try {
      const p = await crearProfesional({
        registro: profesional.registro.trim(), nombre: profesional.nombre.trim(), profesion: profesional.profesion.trim() || undefined,
        tipo_documento: profesional.numero_documento.trim() ? profesional.tipo_documento : undefined, numero_documento: profesional.numero_documento.trim() || undefined,
      });
      setMensaje({ texto: `${p.nombre} queda en el padrón con el registro ${p.registro}. Anota la consulta en ReTHUS cuando la hagas.` });
      setProfesional(PROFESIONAL_VACIO);
      listarProfesionales().then(setProfesionales).catch(() => undefined);
    } catch (e) {
      informar(e);
    }
  }

  async function actualizarProfesional(accion: Promise<ProfesionalRegistrado>) {
    setMensaje(null);
    try {
      const p = await accion;
      setProfesionales((lista) => (lista ?? []).map((x) => (x.id === p.id ? p : x)));
    } catch (e) {
      informar(e);
    }
  }

  async function guardarClave() {
    if (!cambioDeClave) return;
    setMensaje(null);
    try {
      const u = await definirClave(cambioDeClave.usuario, cambioDeClave.clave);
      setMensaje({ texto: `Clave de ${u.usuario} definida. Sus sesiones abiertas se cerraron.` });
      setCambioDeClave(null);
      cargar();
    } catch (e) {
      informar(e);
    }
  }

  async function cambiarEstado(u: UsuarioAdmin) {
    setMensaje(null);
    try {
      const r = await cambiarEstadoUsuario(u.usuario, !u.activo);
      setMensaje({ texto: r.activo ? `${r.usuario} reactivado.` : `${r.usuario} desactivado: pierde acceso de inmediato; su historial permanece.` });
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
      <EstadoMensaje mensaje={mensaje} />

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
          <label>Clave inicial
            <input type="password" value={claveInicial} onChange={(e) => setClaveInicial(e.target.value)} autoComplete="new-password" placeholder={`Opcional, mínimo ${CLAVE_MINIMA}`} />
          </label>
          <button type="button" disabled={!yo || !form.usuario.trim() || !form.nombre.trim() || (claveInicial !== "" && claveInicial.length < CLAVE_MINIMA)} onClick={crear}>Crear usuario</button>
        </div>
        <p className="muted">Con clave, la cuenta inicia sesión y nadie puede firmar escribiendo su nombre. Sin clave, sirve solo para la demostración.</p>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Usuario</th><th>Rol</th><th>Tipo</th><th>Estado</th><th>Sesión</th><th></th></tr></thead>
            <tbody>
              {usuarios?.map((u) => (
                <tr key={u.usuario} data-testid="fila-usuario" className={`fila ${u.activo ? "rutina" : "critico"}`}>
                  <td><code>{u.usuario}</code><span className="secundaria">{u.nombre}</span></td>
                  <td>{nombreRol(u.rol)}</td>
                  <td>{u.tipo === "servicio" ? <span className="tag urgente">Servicio</span> : "Persona"}</td>
                  <td>{u.activo ? <span className="tag exito">Activo</span> : <span className="tag critico">Inactivo</span>}<span className="secundaria">{u.desactivado_en ? `desde ${new Date(u.desactivado_en).toLocaleString("es-CO")}` : `alta por ${u.creado_por}`}</span></td>
                  <td>{u.con_clave ? <span className="tag exito">Con clave</span> : <span className="tag neutro">Sin clave</span>}</td>
                  <td className="acciones">
                    <button type="button" className="secundario" disabled={!yo} aria-label={`Definir la clave de ${u.usuario}`} onClick={() => setCambioDeClave({ usuario: u.usuario, clave: "" })}>Clave</button>
                    <button type="button" className={u.activo ? "peligro" : "secundario"} disabled={!yo} onClick={() => cambiarEstado(u)}>{u.activo ? "Desactivar" : "Activar"}</button>
                  </td>
                </tr>
              ))}
              {usuarios && usuarios.length === 0 && <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 20 }}>Sin usuarios registrados. Mientras tanto cualquiera firma con su nombre (modo demostración).</td></tr>}
            </tbody>
          </table>
        </div>
        {cambioDeClave && (
          <div className="formulario" style={{ marginTop: 10 }} data-testid="cambio-de-clave">
            <label>Clave nueva de {cambioDeClave.usuario}
              <input type="password" value={cambioDeClave.clave} onChange={(e) => setCambioDeClave({ ...cambioDeClave, clave: e.target.value })} autoComplete="new-password" placeholder={`Mínimo ${CLAVE_MINIMA} caracteres`} />
            </label>
            <button type="button" disabled={!yo || cambioDeClave.clave.length < CLAVE_MINIMA} onClick={guardarClave}>Guardar clave</button>
            <button type="button" className="secundario" onClick={() => setCambioDeClave(null)}>Cancelar</button>
          </div>
        )}
      </section>

      <section className="tarjeta" style={{ marginTop: 12 }} data-testid="padron-profesionales">
        <h2>Padrón de profesionales</h2>
        <p className="muted">
          Quién puede firmar documentos clínicos en esta instalación. El triaje verifica contra este padrón y lo muestra en cada documento;
          la consulta en el registro nacional es manual y queda anotada con fecha y quién la hizo.
          {pack?.identidad_profesional.verificacion_en_linea.url ? <> <a href={String(pack.identidad_profesional.verificacion_en_linea.url)} target="_blank" rel="noreferrer">Consultar {pack.identidad_profesional.registro} ›</a></> : null}
        </p>
        <div className="formulario" style={{ marginBottom: 10 }}>
          <label>Registro profesional<input value={profesional.registro} onChange={(e) => setProfesional({ ...profesional, registro: e.target.value })} placeholder="RM 45678" /></label>
          <label>Nombre del profesional<input value={profesional.nombre} onChange={(e) => setProfesional({ ...profesional, nombre: e.target.value })} placeholder="Andrés Rojas" /></label>
          <label>Profesión<input value={profesional.profesion} onChange={(e) => setProfesional({ ...profesional, profesion: e.target.value })} placeholder="Medicina" /></label>
          <label>Tipo de documento
            <select value={profesional.tipo_documento} onChange={(e) => setProfesional({ ...profesional, tipo_documento: e.target.value })}>
              {["CC", "CE", "PA", "PT"].map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label>Número de documento<input value={profesional.numero_documento} onChange={(e) => setProfesional({ ...profesional, numero_documento: e.target.value })} placeholder="Opcional" /></label>
          <button type="button" disabled={!yo || !profesional.registro.trim() || !profesional.nombre.trim()} onClick={crearEnPadron}>Agregar al padrón</button>
        </div>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Registro</th><th>Profesional</th><th>Documento</th><th>Registro nacional</th><th>Estado</th><th></th></tr></thead>
            <tbody>
              {profesionales?.map((p) => (
                <tr key={p.id} data-testid="fila-profesional" className={`fila ${p.activo ? "rutina" : "critico"}`}>
                  <td><code>{p.registro}</code></td>
                  <td>{p.nombre}{p.profesion && <span className="secundaria">{p.profesion}</span>}</td>
                  <td>{p.numero_documento ? <code>{p.tipo_documento} {p.numero_documento}</code> : <span className="muted">—</span>}</td>
                  <td>{p.registro_consultado_en ? <><span className="tag exito">Consultado</span><span className="secundaria">{new Date(p.registro_consultado_en).toLocaleDateString("es-CO")} · {p.registro_consultado_por}</span></> : <span className="tag neutro">Sin consultar</span>}</td>
                  <td>{p.activo ? <span className="tag exito">Activo</span> : <span className="tag critico">Inactivo</span>}</td>
                  <td className="acciones">
                    <button type="button" className="secundario" disabled={!yo} aria-label={`Anotar la consulta en el registro nacional de ${p.nombre}`} onClick={() => actualizarProfesional(anotarConsultaRegistro(p.id))}>Consultado</button>
                    <button type="button" className={p.activo ? "peligro" : "secundario"} disabled={!yo} aria-label={`${p.activo ? "Desactivar" : "Activar"} a ${p.nombre}`} onClick={() => actualizarProfesional(cambiarEstadoProfesional(p.id, !p.activo))}>{p.activo ? "Desactivar" : "Activar"}</button>
                  </td>
                </tr>
              ))}
              {profesionales && profesionales.length === 0 && <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 20 }}>Padrón vacío: ningún profesional saldrá verificado hasta que se agregue.</td></tr>}
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
