import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { obtenerResumen } from "../api";
import { useRol } from "../app/RolContext";
import type { Resumen } from "../types";

/** Inicio del rol: lo pendiente para mí, sin gráficos decorativos (los indicadores viven en Métricas). */
export function InicioPage() {
  const { rol } = useRol();
  const [resumen, setResumen] = useState<Resumen | null>(null);

  useEffect(() => {
    obtenerResumen().then(setResumen).catch(() => setResumen(null));
  }, []);

  const tiene = (ruta: string) => rol.navegacion.some((n) => n.ruta === ruta);
  const r = resumen;

  return (
    <>
      <header className="encabezado">
        <div>
          <h1>Hola, {rol.nombre}</h1>
          <p className="sub">{rol.descripcion}</p>
        </div>
      </header>
      <div className="contadores">
        {rol.veDocumentos && <Contador testid="contador-alertas" valor={r?.alertas_sin_acuse} etiqueta="alertas críticas sin acuse" clase="critico" ruta={tiene("/alertas") ? "/alertas" : undefined} />}
        {tiene("/revision") && <Contador testid="contador-revision" valor={r?.en_revision} etiqueta="en revisión humana" clase="urgente" ruta="/revision" />}
        {tiene("/farmacia") && <Contador testid="contador-recetas" valor={r?.recetas_por_verificar} etiqueta="recetas por verificar" clase="urgente" ruta="/farmacia" />}
        {tiene("/autorizaciones") && <Contador testid="contador-ordenes" valor={r?.ordenes_por_autorizar} etiqueta="órdenes por autorizar" clase="urgente" ruta="/autorizaciones" />}
        {tiene("/entregas") && <Contador testid="contador-enrutados" valor={r?.enrutados} etiqueta="enrutados por entregar" clase="marca" ruta="/entregas" />}
        <Contador testid="contador-entregados" valor={r?.entregados_hoy} etiqueta="entregados hoy" clase="exito" />
        <Contador testid="contador-total" valor={r?.total} etiqueta="documentos en total" clase="neutro" />
      </div>
      <section className="tarjeta" style={{ marginTop: 12 }}>
        <h2>Accesos</h2>
        <ul className="accesos">
          {tiene("/documentos") && <li><Link to="/documentos">Ir a Documentos</Link> · cargar y buscar</li>}
          {tiene("/revision") && <li><Link to="/revision">Ir a la cola de revisión</Link> · aprobar, corregir, rechazar</li>}
          {tiene("/alertas") && <li><Link to="/alertas">Ir a Alertas críticas</Link> · acuse y escalamiento</li>}
          {tiene("/farmacia") && <li><Link to="/farmacia">Ir a Farmacia</Link> · doble verificación</li>}
          {tiene("/autorizaciones") && <li><Link to="/autorizaciones">Ir a Autorizaciones</Link> · aprobar o devolver</li>}
          {tiene("/entregas") && <li><Link to="/entregas">Ir a Entregas</Link> · confirmar destinos</li>}
          {tiene("/metricas") && <li><Link to="/metricas">Ir a Métricas</Link> · indicadores del historial (RN-R1)</li>}
          {tiene("/configuracion") && <li><Link to="/configuracion">Ir a Configuración</Link> · umbrales dentro de rango y simulación (RN-L)</li>}
          {tiene("/administracion") && <li><Link to="/administracion">Ir a Administración</Link> · usuarios, accesos y pack (RN-K)</li>}
          <li><Link to="/demo">Modo demostración</Link> · el recorrido de seis pasos para el jurado</li>
        </ul>
      </section>
      {r && (
        <section className="tarjeta" style={{ marginTop: 12 }}>
          <h2>Por estado</h2>
          <p className="muted">{Object.entries(r.por_estado).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(" · ")}</p>
          <h2 style={{ marginTop: 8 }}>Por prioridad</h2>
          <p className="muted">{Object.entries(r.por_prioridad).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—"}</p>
        </section>
      )}
    </>
  );
}

function Contador({ testid, valor, etiqueta, clase, ruta }: { testid: string; valor: number | undefined; etiqueta: string; clase: string; ruta?: string }) {
  const cuerpo = (
    <>
      <span className={`n ${clase}`}>{valor ?? "—"}</span>
      <span className="muted">{etiqueta}</span>
    </>
  );
  return (
    <div className={`tarjeta contador ${clase}`} data-testid={testid}>
      {ruta ? <Link to={ruta} className="contador-enlace">{cuerpo}</Link> : cuerpo}
    </div>
  );
}
