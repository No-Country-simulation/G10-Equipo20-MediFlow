import { BellRing, CheckCircle2, ClipboardCheck, FileCheck2, Files, GitBranchPlus, Pill, Send, ShieldCheck, Users, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { colaRevision, listarAlertas, listarUsuarios, obtenerConfiguracion, obtenerMetricas, obtenerResumen, puestaEnMarcha } from "../api";
import { etiquetaConcepto, etiquetaEstado, etiquetaMotivo } from "../app/mensajes";
import { calcularPlazo } from "../app/plazos";
import { useRol } from "../app/RolContext";
import { TagPrioridad } from "../components/Tags";
import { Vacio } from "../components/Vacio";
import type { AlertaListada, ItemCola, NivelPrioridad, Resumen } from "../types";

interface Pendiente {
  documento_id: string;
  tipo: "alerta" | "revision";
  nivel: NivelPrioridad | null;
  texto: string;
  vencido: boolean;
  apremia: boolean;
  plazo: string;
  restante: number;
  ruta: string;
}

const ORDEN_PRIORIDAD: NivelPrioridad[] = ["Crítico", "Urgente", "Rutina"];
const CLASE_PRIORIDAD: Record<string, string> = { "Crítico": "critico", Urgente: "urgente", Rutina: "rutina" };

/** Inicio del rol: lo pendiente para mí, ordenado por lo que vence primero. Los indicadores de gestión viven en Métricas. */
export function InicioPage() {
  const { rol } = useRol();
  const [resumen, setResumen] = useState<Resumen | null>(null);
  const [pendientes, setPendientes] = useState<Pendiente[] | null>(null);
  const [gestion, setGestion] = useState<{ propuestas: number; avisos: number } | null>(null);
  const [admin, setAdmin] = useState<{ activos: number; cumplidos: number; total: number } | null>(null);

  const tiene = (ruta: string) => rol.navegacion.some((n) => n.ruta === ruta);
  const veRevision = tiene("/revision");
  const veConfiguracion = tiene("/configuracion");
  const veAdministracion = tiene("/administracion");

  useEffect(() => {
    let activo = true;
    obtenerResumen().then((r) => activo && setResumen(r)).catch(() => activo && setResumen(null));
    if (rol.veDocumentos) {
      Promise.all([
        veRevision ? colaRevision().catch(() => [] as ItemCola[]) : Promise.resolve([] as ItemCola[]),
        listarAlertas({ estado_acuse: "pendiente" }).catch(() => [] as AlertaListada[]),
      ]).then(([cola, alertas]) => {
        if (!activo) return;
        const ahora = new Date();
        const lista: Pendiente[] = [
          ...alertas.map((a) => {
            const p = calcularPlazo(a.emitida_en, a.plazo_minutos, ahora);
            return { documento_id: a.documento_id, tipo: "alerta" as const, nivel: "Crítico" as const, texto: a.concepto ? `Alerta · ${etiquetaConcepto(a.concepto)}` : "Alerta crítica sin acuse",
                     vencido: p.vencido, apremia: p.apremia, plazo: p.texto, restante: p.minutosRestantes, ruta: `/documentos/${encodeURIComponent(a.documento_id)}` };
          }),
          ...cola.map((c) => {
            const p = calcularPlazo(c.creado_en, c.plazo_minutos, ahora);
            return { documento_id: c.documento_id, tipo: "revision" as const, nivel: c.nivel_prioridad, texto: `Revisión · ${etiquetaMotivo(c.motivo_auditoria)}`,
                     vencido: p.vencido, apremia: p.apremia, plazo: p.texto, restante: p.minutosRestantes, ruta: `/documentos/${encodeURIComponent(c.documento_id)}?cola=1` };
          }),
        ];
        // Un documento con alerta y en revisión es un solo pendiente: se fusiona, con el plazo más cercano.
        const porDocumento = new Map<string, Pendiente>();
        for (const p of lista) {
          const previo = porDocumento.get(p.documento_id);
          if (!previo) { porDocumento.set(p.documento_id, p); continue; }
          const alerta = previo.tipo === "alerta" ? previo : p;
          const revision = previo.tipo === "alerta" ? p : previo;
          const primero = previo.restante <= p.restante ? previo : p;
          porDocumento.set(p.documento_id, { ...primero, tipo: "alerta", nivel: "Crítico", texto: `${alerta.texto} · y en revisión`, ruta: revision.ruta });
        }
        const unicos = [...porDocumento.values()].sort((a, b) => a.restante - b.restante);
        setPendientes(unicos.slice(0, 6));
      });
    }
    if (veConfiguracion) {
      Promise.all([obtenerConfiguracion().catch(() => null), obtenerMetricas().catch(() => null)])
        .then(([cfg, m]) => activo && setGestion({ propuestas: cfg?.propuestas.length ?? 0, avisos: m?.avisos.length ?? 0 }));
    }
    if (veAdministracion) {
      Promise.all([listarUsuarios().catch(() => []), puestaEnMarcha().catch(() => null)])
        .then(([u, p]) => activo && setAdmin({ activos: u.filter((x) => x.activo).length, cumplidos: p?.requisitos.filter((r) => r.cumplido).length ?? 0, total: p?.requisitos.length ?? 0 }));
    }
    return () => { activo = false; };
  }, [rol.id, rol.veDocumentos, veRevision, veConfiguracion, veAdministracion]);

  const r = resumen;
  const totalPrioridad = Object.values(r?.por_prioridad ?? {}).reduce((a, b) => a + b, 0);

  return (
    <>
      <header className="encabezado">
        <div>
          <h1>Hola, {rol.nombre}</h1>
          <p className="sub">{rol.descripcion}</p>
        </div>
        <p className="muted" style={{ margin: 0 }}>{new Date().toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long" })}</p>
      </header>

      <div className="contadores">
        {rol.veDocumentos && <Contador testid="contador-alertas" icono={BellRing} valor={r?.alertas_sin_acuse} etiqueta="alertas críticas sin acuse" clase="critico" ruta={tiene("/alertas") ? "/alertas" : undefined} accion="Ir a Alertas críticas" />}
        {veRevision && <Contador testid="contador-revision" icono={ClipboardCheck} valor={r?.en_revision} etiqueta="en revisión humana" clase="urgente" ruta="/revision" accion="Ir a la cola de revisión" />}
        {tiene("/farmacia") && <Contador testid="contador-recetas" icono={Pill} valor={r?.recetas_por_verificar} etiqueta="recetas por verificar" clase="urgente" ruta="/farmacia" accion="Ir a Farmacia" />}
        {tiene("/autorizaciones") && <Contador testid="contador-ordenes" icono={FileCheck2} valor={r?.ordenes_por_autorizar} etiqueta="órdenes por autorizar" clase="urgente" ruta="/autorizaciones" accion="Ir a Autorizaciones" />}
        {tiene("/entregas") && <Contador testid="contador-enrutados" icono={Send} valor={r?.enrutados} etiqueta="enrutados por entregar" clase="marca" ruta="/entregas" accion="Ir a Entregas" />}
        {veConfiguracion && <Contador testid="contador-propuestas" icono={GitBranchPlus} valor={gestion?.propuestas} etiqueta="propuestas de configuración por aprobar" clase="urgente" ruta="/configuracion" accion="Ir a Configuración" />}
        {tiene("/metricas") && <Contador testid="contador-avisos" icono={ShieldCheck} valor={gestion?.avisos} etiqueta="avisos de calidad" clase="marca" ruta="/metricas" accion="Ir a Métricas" />}
        {veAdministracion && <Contador testid="contador-usuarios" icono={Users} valor={admin?.activos} etiqueta="usuarios activos" clase="marca" ruta="/administracion" accion="Ir a Administración" />}
        {veAdministracion && <Contador testid="contador-puesta" icono={ShieldCheck} valor={admin ? `${admin.cumplidos} de ${admin.total}` : undefined} etiqueta="requisitos de puesta en marcha" clase={admin && admin.cumplidos === admin.total ? "exito" : "urgente"} />}
        <Contador testid="contador-entregados" icono={CheckCircle2} valor={r?.entregados_hoy} etiqueta="entregados hoy" clase="exito" />
        <Contador testid="contador-total" icono={Files} valor={r?.total} etiqueta="documentos en total" clase="neutro" ruta={tiene("/documentos") ? "/documentos" : undefined} accion="Ir a Documentos" />
      </div>

      <div className={rol.veDocumentos ? "inicio-grid" : ""}>
        {rol.veDocumentos && (
          <section className="tarjeta" data-testid="vence-primero">
            <div className="panel-cabecera"><h2>Lo que vence primero</h2><span className="muted">alertas y cola, por plazo</span></div>
            {pendientes && pendientes.length === 0 && <Vacio icono={CheckCircle2} titulo="Nada pendiente para ti" texto="Cuando llegue una alerta o un caso a revisión aparecerá aquí, ordenado por lo que vence antes." />}
            {pendientes && pendientes.length > 0 && (
              <ul className="pendientes">
                {pendientes.map((p) => (
                  <li key={`${p.tipo}-${p.documento_id}`}>
                    {p.tipo === "alerta" ? <BellRing size={16} className="ic critico" aria-hidden="true" /> : <ClipboardCheck size={16} className="ic" aria-hidden="true" />}
                    <div className="cuerpo">
                      <Link to={p.ruta}><code>{p.documento_id}</code></Link>
                      <span className="secundaria">{p.texto}</span>
                    </div>
                    <TagPrioridad nivel={p.nivel} />
                    <span className={`plazo ${p.vencido ? "vencido" : p.apremia ? "apremia" : ""}`}>{p.plazo}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        <section className="tarjeta">
          <h2>Por prioridad</h2>
          {totalPrioridad > 0 ? (
            <>
              <div className="barra-prioridad" role="img" aria-label={ORDEN_PRIORIDAD.map((n) => `${n}: ${r?.por_prioridad[n] ?? 0}`).join(", ")}>
                {ORDEN_PRIORIDAD.map((n) => {
                  const v = r?.por_prioridad[n] ?? 0;
                  return v > 0 ? <i key={n} className={CLASE_PRIORIDAD[n]} style={{ flex: v }} /> : null;
                })}
              </div>
              <ul className="leyenda">
                {ORDEN_PRIORIDAD.map((n) => <li key={n}><TagPrioridad nivel={n} /> <strong>{r?.por_prioridad[n] ?? 0}</strong></li>)}
              </ul>
            </>
          ) : <p className="muted">Sin documentos clasificados todavía.</p>}
          <h2 style={{ marginTop: 14 }}>Por estado</h2>
          <ul className="leyenda">
            {Object.entries(r?.por_estado ?? {}).map(([k, v]) => <li key={k}><span className="muted">{etiquetaEstado(k)}</span> <strong>{v}</strong></li>)}
            {r && Object.keys(r.por_estado).length === 0 && <li className="muted">—</li>}
          </ul>
          <p className="muted" style={{ marginTop: 12 }}><Link to="/demo">Modo demostración ›</Link> recorrido guiado con casos sintéticos</p>
        </section>
      </div>
    </>
  );
}

function Contador({ testid, icono: Icono, valor, etiqueta, clase, ruta, accion }: { testid: string; icono: LucideIcon; valor: number | string | undefined; etiqueta: string; clase: string; ruta?: string; accion?: string }) {
  return (
    <div className={`tarjeta contador ${clase}`} data-testid={testid}>
      <Icono size={20} className={`ic ${clase}`} aria-hidden="true" />
      <span className={`n ${clase}`}>{valor ?? "—"}</span>
      <span className="muted">{etiqueta}</span>
      {ruta && <Link to={ruta} className="ir">{accion ?? "Abrir"} ›</Link>}
    </div>
  );
}
