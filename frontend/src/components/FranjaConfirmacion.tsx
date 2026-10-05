import { Check, X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

/**
 * Confirmación en línea de una decisión con consecuencias: nombra qué va a pasar, lleva el foco a Confirmar
 * (Enter confirma) y Esc cancela. Es la misma franja en el detalle, Farmacia y Autorizaciones.
 */
export function FranjaConfirmacion({ children, confirmar, peligro = false, deshabilitado = false, onConfirmar, onCancelar }: {
  children: ReactNode;
  confirmar: string;
  peligro?: boolean;
  deshabilitado?: boolean;
  onConfirmar: () => void;
  onCancelar: () => void;
}) {
  const boton = useRef<HTMLButtonElement>(null);
  useEffect(() => { boton.current?.focus(); }, []);
  return (
    <div className={`confirmacion ${peligro ? "rechazar" : ""}`} data-testid="confirmacion" role="group" aria-label={confirmar}
      onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onCancelar(); } }}>
      <p>{children}</p>
      <div className="acciones">
        <button type="button" ref={boton} className={peligro ? "peligro" : ""} disabled={deshabilitado} onClick={onConfirmar}>
          {peligro ? <X size={16} aria-hidden="true" /> : <Check size={16} aria-hidden="true" />}{confirmar}
        </button>
        <button type="button" className="secundario" onClick={onCancelar}>Cancelar <kbd>Esc</kbd></button>
      </div>
    </div>
  );
}
