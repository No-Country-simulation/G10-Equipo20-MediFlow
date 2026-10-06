import { MessageSquareReply } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { registrarSolicitudTitular, responderSolicitudTitular } from "../api";
import { CANAL, fechaCorta, PRESENTADA_POR, RESULTADO, vencida } from "../app/titular";
import { textoDeError, type Mensaje } from "./EstadoMensaje";
import { Vacio } from "./Vacio";
import type { DocumentoDePaciente, SolicitudTitular } from "../types";

interface Props {
  pacienteId: number;
  documentos: DocumentoDePaciente[];
  solicitudes: SolicitudTitular[];
  puedeRegistrar: boolean;
  puedeResponder: boolean;
  onCambio: (solicitudes: SolicitudTitular[]) => void;
  onMensaje: (mensaje: Mensaje | null) => void;
}

/**
 * RN-M6: el titular no entra al sistema. El auditor registra en la ficha que pidió revisión humana de una
 * decisión automatizada, y una persona responde dentro del plazo legal del pack. Todo queda firmado.
 */
export function SolicitudesTitular({ pacienteId, documentos, solicitudes, puedeRegistrar, puedeResponder, onCambio, onMensaje }: Props) {
  const [registrando, setRegistrando] = useState(false);
  const [documentoId, setDocumentoId] = useState("");
  const [presentadaPor, setPresentadaPor] = useState<SolicitudTitular["presentada_por"]>("titular");
  const [canal, setCanal] = useState<SolicitudTitular["canal"]>("presencial");
  const [motivo, setMotivo] = useState("");
  const [respondiendo, setRespondiendo] = useState<number | null>(null);
  const [resultado, setResultado] = useState<"mantenida" | "corregida">("mantenida");
  const [respuesta, setRespuesta] = useState("");
  const [enviando, setEnviando] = useState(false);

  const documentosUnicos = documentos.filter((d, i) => documentos.findIndex((o) => o.documento_id === d.documento_id) === i);
  const conPendiente = new Set(solicitudes.filter((s) => s.estado === "pendiente").map((s) => s.documento_id));
  const pendientes = solicitudes.filter((s) => s.estado === "pendiente").length;

  function abrirRegistro() {
    setDocumentoId(documentosUnicos.find((d) => !conPendiente.has(d.documento_id))?.documento_id ?? "");
    setPresentadaPor("titular"); setCanal("presencial"); setMotivo("");
    onMensaje(null);
    setRegistrando(true);
  }

  async function registrar() {
    setEnviando(true);
    try {
      const nueva = await registrarSolicitudTitular(pacienteId, { documento_id: documentoId, presentada_por: presentadaPor, canal, motivo: motivo.trim() });
      onCambio([nueva, ...solicitudes]);
      setRegistrando(false);
      onMensaje({ texto: `Solicitud registrada. Hay plazo hasta el ${fechaCorta(nueva.vence_en)} para responder.` });
    } catch (e) {
      onMensaje({ texto: textoDeError(e), error: true });
    } finally {
      setEnviando(false);
    }
  }

  async function responder(id: number) {
    setEnviando(true);
    try {
      const respondida = await responderSolicitudTitular(id, { resultado, respuesta: respuesta.trim() });
      onCambio(solicitudes.map((s) => (s.id === id ? respondida : s)));
      setRespondiendo(null);
      setRespuesta("");
      onMensaje({ texto: `Solicitud respondida: ${RESULTADO[resultado].toLowerCase()}. Queda firmada en la ficha.` });
    } catch (e) {
      onMensaje({ texto: textoDeError(e), error: true });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section className="tarjeta" style={{ marginTop: 12 }} data-testid="solicitudes-titular">
      <div className="encabezado" style={{ marginBottom: 8 }}>
        <div>
          <h2>Solicitudes del titular{pendientes > 0 && <span className="muted" style={{ fontWeight: 400 }}> · {pendientes} pendiente{pendientes === 1 ? "" : "s"}</span>}</h2>
          <p className="muted" style={{ margin: 0 }}>El paciente puede pedir que una persona revise una decisión automatizada sobre uno de sus documentos. Se responde dentro del plazo legal.</p>
        </div>
        {puedeRegistrar && !registrando && documentosUnicos.length > 0 && (
          <button type="button" className="secundario" onClick={abrirRegistro}><MessageSquareReply size={16} aria-hidden="true" />Registrar solicitud</button>
        )}
      </div>

      {registrando && (
        <div className="tarjeta correccion" data-testid="registro-solicitud">
          <div className="campos">
            <label className="ancho">
              Documento cuya decisión se revisa
              <select value={documentoId} onChange={(e) => setDocumentoId(e.target.value)}>
                <option value="">Elige el documento…</option>
                {documentosUnicos.map((d) => <option key={d.documento_id} value={d.documento_id} disabled={conPendiente.has(d.documento_id)}>{d.documento_id}{d.tipo ? ` · ${d.tipo}` : ""}{conPendiente.has(d.documento_id) ? " (ya tiene una pendiente)" : ""}</option>)}
              </select>
            </label>
            <label>
              Quién la presenta
              <select value={presentadaPor} onChange={(e) => setPresentadaPor(e.target.value as SolicitudTitular["presentada_por"])}>
                <option value="titular">El titular</option>
                <option value="representante">Su representante</option>
              </select>
            </label>
            <label>
              Canal
              <select value={canal} onChange={(e) => setCanal(e.target.value as SolicitudTitular["canal"])}>
                <option value="presencial">Presencial</option>
                <option value="telefono">Teléfono</option>
                <option value="correo">Correo</option>
                <option value="escrito">Escrito</option>
              </select>
            </label>
            <label className="ancho">Motivo del titular<input value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Obligatorio: qué pide revisar y por qué" /></label>
          </div>
          <div className="acciones" style={{ marginTop: 12 }}>
            <button type="button" disabled={!documentoId || !motivo.trim() || enviando} onClick={registrar}>Registrar</button>
            <button type="button" className="secundario" onClick={() => setRegistrando(false)}>Cancelar</button>
          </div>
        </div>
      )}

      {solicitudes.length === 0 && !registrando && <Vacio icono={MessageSquareReply} titulo="Sin solicitudes" texto="Ningún titular ha pedido revisión humana de una decisión sobre sus documentos." />}
      <ul className="accesos">
        {solicitudes.map((s) => (
          <li key={s.id} data-testid="solicitud-titular">
            <span className={`tag ${s.estado === "pendiente" ? (vencida(s) ? "critico" : "urgente") : "exito"}`}>
              {s.estado === "pendiente" ? (vencida(s) ? "Vencida" : "Pendiente") : RESULTADO[s.resultado ?? "mantenida"]}
            </span>{" "}
            <Link to={`/documentos/${encodeURIComponent(s.documento_id)}`}><code>{s.documento_id}</code></Link>
            {" · "}presentada por {PRESENTADA_POR[s.presentada_por]} {CANAL[s.canal]} el {fechaCorta(s.registrada_en)} · registró {s.registrada_por}
            <span className="secundaria">Motivo: {s.motivo}</span>
            {s.estado === "pendiente"
              ? <span className="secundaria">Plazo para responder: {fechaCorta(s.vence_en)}</span>
              : <span className="secundaria">Respondió {s.respondida_por} el {fechaCorta(s.respondida_en)}: {s.respuesta}</span>}
            {s.estado === "pendiente" && puedeResponder && respondiendo !== s.id && (
              <div className="acciones" style={{ marginTop: 6 }}>
                <button type="button" className="secundario" onClick={() => { setRespondiendo(s.id); setResultado("mantenida"); setRespuesta(""); onMensaje(null); }}>Responder</button>
              </div>
            )}
            {respondiendo === s.id && (
              <div className="tarjeta correccion" data-testid="respuesta-solicitud">
                <div className="campos">
                  <label>
                    Resultado de la revisión
                    <select value={resultado} onChange={(e) => setResultado(e.target.value as "mantenida" | "corregida")}>
                      <option value="mantenida">Decisión mantenida</option>
                      <option value="corregida">Decisión corregida</option>
                    </select>
                  </label>
                  <label className="ancho">Respuesta al titular<input value={respuesta} onChange={(e) => setRespuesta(e.target.value)} placeholder="Obligatoria: qué se revisó y qué se decidió" /></label>
                </div>
                <div className="acciones" style={{ marginTop: 12 }}>
                  <button type="button" disabled={!respuesta.trim() || enviando} onClick={() => responder(s.id)}>Guardar respuesta</button>
                  <button type="button" className="secundario" onClick={() => setRespondiendo(null)}>Cancelar</button>
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
