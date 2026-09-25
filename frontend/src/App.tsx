import { useState } from "react";

import { consultarDocumento } from "./api";
import { FhirModal, ImpresionModal, QueueMonitorModal } from "./components/Modales";
import { AlertaCriticaScreen } from "./components/screens/AlertaCriticaScreen";
import { CockpitScreen } from "./components/screens/CockpitScreen";
import { EntregaScreen } from "./components/screens/EntregaScreen";
import { IngestaScreen } from "./components/screens/IngestaScreen";
import { ProcesamientoScreen } from "./components/screens/ProcesamientoScreen";
import { RevisionHumanaScreen } from "./components/screens/RevisionHumanaScreen";
import type { DocumentoDetalle } from "./types";

type Paso = "ingesta" | "procesamiento" | "cockpit" | "alerta" | "revision" | "entrega";
type ModalAbierto = "cola" | "fhir" | "impresion" | null;

const PASOS: Paso[] = ["ingesta", "procesamiento", "cockpit", "alerta", "revision", "entrega"];

export default function App() {
  const [paso, setPaso] = useState<Paso>("ingesta");
  const [detalle, setDetalle] = useState<DocumentoDetalle | null>(null);
  const [modal, setModal] = useState<ModalAbierto>(null);

  async function refrescar(documentoId: string): Promise<DocumentoDetalle> {
    const nuevo = await consultarDocumento(documentoId);
    setDetalle(nuevo);
    return nuevo;
  }

  async function onEnviado(d: DocumentoDetalle) {
    const completo = await refrescar(d.documento_id);
    setDetalle(completo);
    setPaso("procesamiento");
  }

  function despuesDelCockpit() {
    if (!detalle?.resultado) return setPaso("ingesta");
    if (detalle.estado === "EN_REVISION_HUMANA") return setPaso("revision");
    if (detalle.alerta && detalle.alerta.estado_acuse === "pendiente") return setPaso("alerta");
    setPaso("entrega");
  }

  async function onAcusada() {
    if (!detalle) return;
    const nuevo = await refrescar(detalle.documento_id);
    setPaso(nuevo.estado === "EN_REVISION_HUMANA" ? "revision" : "entrega");
  }

  async function onResuelto(documentoId: string) {
    await refrescar(documentoId);
    setPaso("cockpit");
  }

  return (
    <div className="app">
      <header className="app-cabecera">
        <h1>MediFlow <span className="muted">· triaje, extracción y enrutamiento · Pack CO</span></h1>
        <nav>
          <button type="button" className="secundario" onClick={() => setModal("cola")}>Monitor de cola</button>
          <button type="button" className="secundario" disabled={!detalle?.resultado} onClick={() => setModal("fhir")}>HL7 FHIR</button>
          <button type="button" className="secundario" disabled={!detalle?.resultado} onClick={() => setModal("impresion")}>Imprimir</button>
        </nav>
      </header>

      <ol className="pasos">
        {PASOS.map((p) => <li key={p} className={p === paso ? "activo" : ""}>{p}</li>)}
      </ol>

      {paso === "ingesta" && <IngestaScreen onEnviado={onEnviado} />}
      {paso === "procesamiento" && detalle && <ProcesamientoScreen detalle={detalle} onContinuar={() => setPaso("cockpit")} />}
      {paso === "cockpit" && detalle && <CockpitScreen detalle={detalle} onContinuar={despuesDelCockpit} />}
      {paso === "alerta" && detalle && <AlertaCriticaScreen detalle={detalle} onAcusada={onAcusada} />}
      {paso === "revision" && <RevisionHumanaScreen documentoInicial={detalle?.documento_id ?? null} onResuelto={onResuelto} />}
      {paso === "entrega" && detalle && <EntregaScreen detalle={detalle} onReiniciar={() => { setDetalle(null); setPaso("ingesta"); }} />}

      {modal === "cola" && <QueueMonitorModal onCerrar={() => setModal(null)} />}
      {modal === "fhir" && detalle?.resultado && <FhirModal resultado={detalle.resultado} onCerrar={() => setModal(null)} />}
      {modal === "impresion" && detalle?.resultado && <ImpresionModal resultado={detalle.resultado} onCerrar={() => setModal(null)} />}
    </div>
  );
}
