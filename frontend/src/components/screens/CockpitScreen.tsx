import { urlOriginal, urlVistaPrevia } from "../../api";
import type { DocumentoDetalle } from "../../types";
import { HistorialDecisiones } from "../HistorialDecisiones";
import { PrioridadBadge } from "../PrioridadBadge";

interface Props {
  detalle: DocumentoDetalle;
  onContinuar: () => void;
}

/** Pantalla 3: cockpit clínico con el JSON del brief leído por una persona. */
export function CockpitScreen({ detalle, onContinuar }: Props) {
  const r = detalle.resultado;
  if (!r) {
    return (
      <section className="pantalla">
        <h2>3. Cockpit</h2>
        <p className="error">Sin resultado: {detalle.codigo_error ?? detalle.estado}</p>
      </section>
    );
  }
  const { clasificacion: c, extraccion: e, evaluacion: ev, enrutamiento: en } = r;
  const sv = e.signos_vitales;
  const retenidas = Object.entries(en.entregas_retenidas);
  const esArchivo = detalle.formato === "pdf" || detalle.formato === "png" || detalle.formato === "jpeg";

  return (
    <section className="pantalla">
      <header className="cabecera-cockpit">
        <h2>3. Cockpit clínico</h2>
        <PrioridadBadge nivel={c.nivel_prioridad} />
      </header>

      <div className="grid-2">
        <div className="tarjeta">
          <h3>Clasificación</h3>
          <dl>
            <dt>Tipo</dt><dd>{c.tipo}</dd>
            <dt>Setting</dt><dd>{c.setting}</dd>
            <dt>Especialidad</dt><dd>{c.especialidad} · {c.dominio}</dd>
            <dt>Confianza</dt><dd>{c.score_confianza.toFixed(2)}</dd>
          </dl>
        </div>

        <div className="tarjeta">
          <h3>Paciente</h3>
          <dl>
            <dt>Nombre</dt><dd>{e.paciente.nombre ?? "—"}</dd>
            <dt>Edad</dt><dd>{e.paciente.edad ?? "—"}</dd>
            <dt>Documento</dt>
            <dd>{e.paciente.documento.tipo} {e.paciente.documento.valor ?? ""} <em>({e.paciente.documento.estado})</em></dd>
            <dt>Profesional</dt><dd>{e.profesional.nombre ?? "—"} {e.profesional.registro_profesional ?? ""}</dd>
            <dt>Fecha</dt><dd>{e.fecha_documento ?? "—"}</dd>
          </dl>
        </div>

        <div className="tarjeta">
          <h3>Hallazgos críticos y signos vitales</h3>
          {e.hallazgos_criticos_detectados.length > 0 ? (
            <ul className="chips">{e.hallazgos_criticos_detectados.map((h) => <li key={h} className="chip critico">{h}</li>)}</ul>
          ) : <p className="muted">Sin hallazgos críticos.</p>}
          <p>
            FR {sv.FR ?? "—"} · SpO2 {sv.SpO2 ?? "—"} · FC {sv.FC ?? "—"} · PAS {sv.PAS ?? "—"} · T {sv.Temp ?? "—"}
          </p>
          <p><strong>NEWS2 total: {sv.NEWS2_total ?? "no aplica"}</strong></p>
        </div>

        <div className="tarjeta">
          <h3>Diagnósticos y medicamentos</h3>
          <ul>
            {e.diagnosticos.map((d, i) => (
              <li key={i}>{d.texto} <code>{d.cie10_sugerido ?? ""}</code> <code>{d.cie11_sugerido ?? ""}</code></li>
            ))}
          </ul>
          {e.medicamentos.length > 0 && (
            <ul>
              {e.medicamentos.map((m, i) => (
                <li key={i}>
                  {m.dci} {m.dosis ?? ""} {m.via ?? ""} {m.frecuencia ?? ""}
                  {m.alto_riesgo && <span className="chip critico"> alto riesgo </span>}
                  {m.control_especial && <span className="chip urgente"> control especial </span>}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="tarjeta">
          <h3>Enrutamiento</h3>
          <p>Principal: <strong>{en.destino_principal}</strong></p>
          {en.destinos_secundarios.length > 0 && <p>Secundarios: {en.destinos_secundarios.join(", ")}</p>}
          {en.destinos_tras_revision.length > 0 && <p>Tras revisión: {en.destinos_tras_revision.join(", ")}</p>}
          {retenidas.length > 0 && (
            <p className="aviso">Entrega retenida: {retenidas.map(([d, m]) => `${d} (${m})`).join("; ")}</p>
          )}
          {en.documentacion_incompleta && <p className="aviso">Documentación incompleta: vuelve al solicitante (RN-E5).</p>}
          <p className="muted">{en.justificacion_enrutamiento}</p>
        </div>

        <div className="tarjeta">
          <h3>Evaluación</h3>
          {ev.requiere_auditoria_humana ? (
            <p className="aviso">Requiere revisión humana: <code>{ev.motivo_auditoria}</code></p>
          ) : <p>No requiere revisión humana.</p>}
          {ev.campos_dudosos.length > 0 && <p>Campos dudosos: {ev.campos_dudosos.join(", ")}</p>}
          <p className="muted">Pack {r.pack_pais} · reglas v{r.version_reglas} · respaldo {r.status_backup}</p>
        </div>
      </div>

      {esArchivo && (
        <div className="tarjeta original">
          <h3>Documento original</h3>
          <p>
            <a href={urlOriginal(detalle.documento_id)} target="_blank" rel="noreferrer">Ver original</a>
            {detalle.nombre_archivo && <span className="muted"> · {detalle.nombre_archivo}</span>}
            {detalle.num_paginas && detalle.num_paginas > 1 && <span className="muted"> · {detalle.num_paginas} páginas</span>}
          </p>
          {detalle.formato === "pdf" ? (
            <img className="vista-previa" src={urlVistaPrevia(detalle.documento_id, 1)} alt="Página 1 del original" />
          ) : (
            <img className="vista-previa" src={urlOriginal(detalle.documento_id)} alt="Imagen original" />
          )}
        </div>
      )}

      <h3>Historial de decisiones (RN-G2)</h3>
      <HistorialDecisiones historial={r.historial_decisiones} />

      <button type="button" onClick={onContinuar}>Continuar</button>
    </section>
  );
}
