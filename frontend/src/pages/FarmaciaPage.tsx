import { Pill } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { colaFarmacia, verificarReceta } from "../api";
import { useEstadoMotor } from "../app/motor";
import { AvisoCaidaEnBandeja } from "../components/AvisoSistema";
import { EstadoMensaje, textoDeError, type Mensaje } from "../components/EstadoMensaje";
import { useUsuario } from "../app/usuario";
import { FranjaConfirmacion } from "../components/FranjaConfirmacion";
import { TagPrioridad } from "../components/Tags";
import { Vacio } from "../components/Vacio";
import type { RecetaPorVerificar } from "../types";

/** Farmacia: recetas por verificar. Alto riesgo y control especial exigen dos personas distintas (RN-E6, RN-J6, RN-CO9). */
export function FarmaciaPage() {
  const [recetas, setRecetas] = useState<RecetaPorVerificar[] | null>(null);
  const [usuario] = useUsuario();
  const [mensaje, setMensaje] = useState<Mensaje | null>(null);
  const [error, setError] = useState<string | null>(null);
  const motor = useEstadoMotor();
  const caido = motor?.degradado ?? false;

  const cargar = () => colaFarmacia().then(setRecetas).catch(() => setError("No hay conexión con la API."));
  useEffect(() => { cargar(); }, []);

  const [porConfirmar, setPorConfirmar] = useState<string | null>(null);

  async function verificar(documentoId: string) {
    setPorConfirmar(null);
    setMensaje(null);
    try {
      const r = await verificarReceta(documentoId);
      setMensaje({ texto: r.completa ? `${documentoId} verificada (${r.verificaciones.length} de ${r.requeridas}). Queda ${r.estado === "ENTREGADO" ? "entregada" : "en curso"}.` : `${documentoId}: primera verificación registrada; falta la segunda por otra persona` });
      cargar();
    } catch (e) {
      setMensaje({ texto: textoDeError(e), error: true });
    }
  }

  const yo = usuario.trim();

  return (
    <>
      <header className="encabezado">
        <div>
          <h1>Farmacia</h1>
          <p className="sub">Recetas enrutadas a Farmacia. Las de alto riesgo y control especial necesitan dos verificaciones de personas distintas.</p>
        </div>
      </header>
      {motor && caido && <AvisoCaidaEnBandeja estado={motor} que="recetas" />}
      <EstadoMensaje mensaje={mensaje} />
      {error && <p className="error">{error}</p>}
      <section className="tarjeta" style={{ padding: 0 }}>
        <div className="scroll">
          <table className="tabla-densa">
            <thead><tr><th>Receta</th><th>Medicamentos (DCI)</th><th>Riesgo</th><th>Verificaciones</th><th></th></tr></thead>
            <tbody>
              {recetas?.map((r) => {
                const hechas = r.verificaciones.length;
                const yaFirme = r.verificaciones.some((v) => v.usuario === yo);
                const siguiente = hechas === 0 ? "Primera verificación" : "Segunda verificación";
                return (
                  <tr key={`${r.documento_id}-${r.version}`} data-testid="fila-receta" className={`fila ${r.alto_riesgo || r.control_especial ? "critico" : "rutina"}`}>
                    <td>
                      <Link to={`/documentos/${encodeURIComponent(r.documento_id)}`}><code>{r.documento_id}</code></Link>
                      <span className="secundaria">{r.fecha_documento ?? ""} · <TagPrioridad nivel={r.nivel_prioridad} /></span>
                    </td>
                    <td>
                      <ul style={{ margin: 0, paddingLeft: 16 }}>
                        {r.medicamentos.map((m, i) => (
                          <li key={i}>{m.dci} {m.dosis ?? ""}{m.dosis_valor && <span className="muted"> (leído {m.dosis_valor})</span>} {m.via ?? ""} {m.frecuencia ?? ""}</li>
                        ))}
                      </ul>
                    </td>
                    <td>
                      {r.alto_riesgo && <span className="tag critico">alto riesgo</span>}{" "}
                      {r.control_especial && <span className="tag urgente">control especial</span>}
                      {!r.alto_riesgo && !r.control_especial && <span className="muted">—</span>}
                    </td>
                    <td>
                      <strong>{hechas} de {r.verificaciones_requeridas}</strong>
                      {r.verificaciones.length > 0 && <span className="secundaria">{r.verificaciones.map((v) => v.usuario).join(", ")}</span>}
                    </td>
                    <td>
                      {porConfirmar === r.documento_id ? (
                        <FranjaConfirmacion confirmar="Confirmar verificación" onConfirmar={() => verificar(r.documento_id)} onCancelar={() => setPorConfirmar(null)}>
                          ¿Registrar la {hechas === 0 ? "primera" : "segunda"} verificación de <strong>{r.documento_id}</strong> ({r.medicamentos.map((m) => `${m.dci} ${m.dosis ?? ""}`.trim()).join(", ")}) como <strong>{yo}</strong>?
                        </FranjaConfirmacion>
                      ) : (
                        <button type="button" disabled={!yo || yaFirme} onClick={() => setPorConfirmar(r.documento_id)} aria-label={`${siguiente}: ${r.documento_id}`}>{siguiente}</button>
                      )}
                      {yaFirme && <span className="secundaria">Requiere otra persona: la primera verificación la hiciste tú.</span>}
                    </td>
                  </tr>
                );
              })}
              {recetas && recetas.length === 0 && <tr><td colSpan={5}>{caido
                ? <Vacio icono={Pill} titulo="Ninguna receta lista para verificar" texto="Las que estén entre los documentos sin leer llegarán cuando se transcriban." />
                : <Vacio icono={Pill} titulo="No hay recetas por verificar" texto="Las fórmulas enrutadas a Farmacia llegan aquí. Las de alto riesgo y control especial piden dos firmas." />}</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
