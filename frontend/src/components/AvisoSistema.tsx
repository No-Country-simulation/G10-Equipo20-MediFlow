import { ServerCrash } from "lucide-react";
import type { ReactNode } from "react";

import type { EstadoMotor } from "../app/motor";

/**
 * Estado del sistema cuando el motor de extracción no responde. Va en ámbar: no es una alerta clínica
 * (eso es rojo) ni un estado normal (eso es el verde de la marca), sino una contingencia que cambia cómo trabajar.
 */
export function AvisoSistemaDegradado({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section className="aviso-sistema urgente" data-testid="sistema-degradado" aria-labelledby="aviso-sistema-titulo">
      <ServerCrash size={22} aria-hidden="true" />
      <div>
        <strong id="aviso-sistema-titulo">{titulo}</strong>
        {children}
      </div>
    </section>
  );
}

/** Título común del aviso: la causa y desde cuándo. */
export function tituloCaida(desde: string | null): string {
  return conPunto(`El motor de extracción no está respondiendo${desde ? ` desde las ${horaCorta(desde)}` : ""}`);
}

/**
 * Para Farmacia y Autorizaciones: lo que la caída retiene sin leer también les falta a ellas.
 * Dice cuántos documentos esperan, quién los transcribe y que la bandeja puede estar incompleta (RN-P2).
 */
export function AvisoCaidaEnBandeja({ estado, que }: { estado: EstadoMotor; que: string }) {
  return (
    <AvisoSistemaDegradado titulo={tituloCaida(estado.desde)}>
      <p>{estado.enEspera} documentos esperan transcripción en la cola de revisión. Las {que} que haya entre ellos llegarán aquí cuando el auditor clínico los transcriba, así que esta bandeja puede estar incompleta.</p>
    </AvisoSistemaDegradado>
  );
}

/** Hora corta para "desde las …". */
export function horaCorta(iso: string | Date): string {
  return new Date(iso).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" });
}

/** Cierra una frase con punto sin duplicarlo cuando ya termina en uno, como en "a. m.". */
export function conPunto(frase: string): string {
  return frase.endsWith(".") ? frase : `${frase}.`;
}
