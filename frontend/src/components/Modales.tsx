import { useEffect, useState } from "react";

import { colaRevision } from "../api";
import type { ItemCola, ResultadoTriaje } from "../types";
import { PrioridadBadge } from "./PrioridadBadge";
import { formatearPlazo } from "./screens/RevisionHumanaScreen";

function Modal({ titulo, onCerrar, children }: { titulo: string; onCerrar: () => void; children: React.ReactNode }) {
  return (
    <div className="modal-fondo" role="dialog" aria-label={titulo}>
      <div className="modal">
        <header>
          <h3>{titulo}</h3>
          <button type="button" className="secundario" onClick={onCerrar}>Cerrar</button>
        </header>
        {children}
      </div>
    </div>
  );
}

/** Monitor de la cola de revisión (RN-J1). */
export function QueueMonitorModal({ onCerrar }: { onCerrar: () => void }) {
  const [cola, setCola] = useState<ItemCola[]>([]);
  useEffect(() => {
    colaRevision().then(setCola).catch(() => setCola([]));
  }, []);
  return (
    <Modal titulo="Monitor de cola de revisión" onCerrar={onCerrar}>
      <ul className="cola">
        {cola.map((i) => (
          <li key={i.documento_id}>
            <PrioridadBadge nivel={i.nivel_prioridad} /> <code>{i.documento_id}</code> · {i.motivo_auditoria} · plazo {formatearPlazo(i.plazo_minutos)}
          </li>
        ))}
        {cola.length === 0 && <li className="muted">Sin documentos en revisión.</li>}
      </ul>
    </Modal>
  );
}

/** Vista previa HL7 FHIR. RN-CO17: el mapeo a FHIR y el envío del RDA son del software de HCE, no de MediFlow. Solo maqueta. */
export function FhirModal({ resultado, onCerrar }: { resultado: ResultadoTriaje; onCerrar: () => void }) {
  const p = resultado.extraccion.paciente;
  const bundle = {
    resourceType: "Bundle",
    type: "collection",
    meta: { note: "Maqueta ilustrativa. Fuera del MVP por RN-CO17." },
    entry: [
      {
        resource: {
          resourceType: "Patient",
          identifier: p.documento.valor ? [{ system: `urn:co:${p.documento.tipo}`, value: p.documento.valor }] : [],
          name: p.nombre ? [{ text: p.nombre }] : [],
        },
      },
      ...resultado.extraccion.diagnosticos.map((d) => ({
        resource: {
          resourceType: "Condition",
          code: {
            coding: [
              d.cie10_sugerido && { system: "http://hl7.org/fhir/sid/icd-10", code: d.cie10_sugerido },
              d.cie11_sugerido && { system: "http://id.who.int/icd/release/11/mms", code: d.cie11_sugerido },
            ].filter(Boolean),
            text: d.texto,
          },
        },
      })),
      {
        resource: {
          resourceType: "Flag",
          status: "active",
          code: { text: `Prioridad MediFlow: ${resultado.clasificacion.nivel_prioridad}` },
        },
      },
    ],
  };
  return (
    <Modal titulo="Vista previa HL7 FHIR (maqueta, RN-CO17)" onCerrar={onCerrar}>
      <pre className="json">{JSON.stringify(bundle, null, 2)}</pre>
    </Modal>
  );
}

/** Impresión del JSON de resultado. */
export function ImpresionModal({ resultado, onCerrar }: { resultado: ResultadoTriaje; onCerrar: () => void }) {
  return (
    <Modal titulo="Impresión del resultado" onCerrar={onCerrar}>
      <button type="button" onClick={() => window.print()}>Imprimir</button>
      <pre className="json imprimible">{JSON.stringify(resultado, null, 2)}</pre>
    </Modal>
  );
}
