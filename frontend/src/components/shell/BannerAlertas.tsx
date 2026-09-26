import { OctagonAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listarAlertas } from "../../api";
import { etiquetaConcepto } from "../../app/mensajes";
import { calcularPlazo } from "../../app/plazos";
import type { AlertaListada } from "../../types";

const INTERVALO_MS = 30_000;

/** Un solo banner para todas las alertas críticas sin acuse (RN-F1, RN-F2, RN-Q4). */
export function BannerAlertas() {
  const [alertas, setAlertas] = useState<AlertaListada[]>([]);
  const [ahora, setAhora] = useState(() => new Date());

  useEffect(() => {
    let activo = true;
    const cargar = () => listarAlertas({ estado_acuse: "pendiente" }).then((a) => activo && setAlertas(a)).catch(() => activo && setAlertas([]));
    cargar();
    const refresco = setInterval(cargar, INTERVALO_MS);
    const reloj = setInterval(() => setAhora(new Date()), 15_000);
    return () => {
      activo = false;
      clearInterval(refresco);
      clearInterval(reloj);
    };
  }, []);

  if (alertas.length === 0) return null;
  const primera = alertas[0];
  const plazo = calcularPlazo(primera.emitida_en, primera.plazo_minutos, ahora);
  const cuantas = alertas.length;
  return (
    <div className={`banner-alertas ${plazo.vencido ? "escalada" : ""}`} role="status" aria-label="Alertas críticas">
      <OctagonAlert className="punto" size={22} aria-hidden="true" />
      <strong>{cuantas === 1 ? "1 alerta crítica sin acuse" : `${cuantas} alertas críticas sin acuse`}</strong>
      <span className="detalle">
        <code>{primera.documento_id}</code>
        {primera.concepto && <> · {etiquetaConcepto(primera.concepto)}</>}
        {" · "}
        {/* La cuenta regresiva cambia cada 15 s: se oculta al lector de pantalla para que no la anuncie en bucle. */}
        <span className={`plazo ${plazo.vencido ? "vencido" : plazo.apremia ? "apremia" : ""}`} aria-hidden="true">{plazo.texto}</span>
        <span className="oculto-visual">{plazo.vencido ? "vencida" : "en plazo"}</span>
        {plazo.vencido && " · escalada al siguiente rol"}
      </span>
      <Link to="/alertas">Ver alertas</Link>
    </div>
  );
}
