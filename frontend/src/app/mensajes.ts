/** Textos de interfaz. Los códigos del backend se traducen aquí; nunca se muestran crudos. */
import type { EstadoDocumento } from "../types";

export const ETIQUETA_ESTADO: Record<EstadoDocumento, string> = {
  RECIBIDO: "Recibido",
  VALIDADO: "Validado",
  CLASIFICADO: "Clasificado",
  EXTRAIDO: "Extraído",
  EVALUADO: "Evaluado",
  EN_REVISION_HUMANA: "Revisión humana",
  RESUELTO: "Resuelto",
  ENRUTADO: "Enrutado",
  ENTREGADO: "Entregado",
  RECHAZADO: "Rechazado",
  FALLO_TECNICO: "Fallo técnico",
};

export const MENSAJE_RECHAZO: Record<string, string> = {
  formato_no_soportado: "Solo se aceptan PDF, PNG y JPG.",
  extension_no_coincide: "La extensión no coincide con el contenido del archivo.",
  archivo_vacio: "El archivo está vacío.",
  archivo_invalido: "El archivo no se pudo decodificar.",
  contenido_no_reconocido: "El contenido no es un documento válido.",
  pdf_corrupto: "El PDF está dañado o no es compatible.",
  pdf_cifrado: "No se admiten PDF cifrados.",
  pdf_sin_paginas: "El PDF no tiene páginas.",
  imagen_corrupta: "La imagen está dañada o excede los límites de seguridad.",
  limite_paginas: "El PDF supera el máximo de páginas permitido.",
  limite_caracteres: "El documento supera el máximo de texto permitido.",
  tamano_excedido: "El archivo supera el tamaño máximo. No se recorta: se rechaza (RN-O5).",
  nombre_invalido: "El nombre del archivo no es válido.",
};

export const MOTIVO_AUDITORIA: Record<string, string> = {
  receta_incompleta_norma: "Fórmula incompleta según norma",
  control_especial_sin_recetario: "Control especial sin recetario oficial",
  cobertura_no_informada: "Cobertura no informada",
  cobertura_no_configurada: "Cobertura sin reglas cargadas",
  fuera_de_alcance: "Fuera del alcance clínico",
  fallo_tecnico: "Fallo técnico",
  documentacion_incompleta: "Documentación incompleta",
  clasificacion_baja_confianza: "Clasificación con baja confianza",
  no_clasificable: "No clasificable",
  campo_dudoso: "Campo bajo el umbral",
  ambiguo: "Dato ambiguo",
  ilegible: "Documento ilegible",
  dosis_ambigua: "Dosis ambigua",
  fecha_ambigua: "Fecha ambigua",
  identidad_invalida: "Identificador inválido",
  profesional_no_identificable: "Profesional no identificable",
  signos_vitales_sin_escala: "Signos vitales sin escala aplicable",
  critico_baja_confianza: "Crítico con baja confianza",
  campo_obligatorio_faltante: "Falta un campo obligatorio",
};

export function mensajeDeRechazo(codigo: string | null | undefined): string {
  if (!codigo) return "El documento fue rechazado.";
  return MENSAJE_RECHAZO[codigo] ?? `El documento fue rechazado (${codigo}).`;
}

export function etiquetaMotivo(codigo: string | null | undefined): string {
  if (!codigo) return "";
  return MOTIVO_AUDITORIA[codigo] ?? codigo;
}

export function claseEstado(estado: EstadoDocumento): "exito" | "critico" | "marca" | "neutro" {
  if (estado === "ENTREGADO") return "exito";
  if (estado === "RECHAZADO") return "critico";
  if (estado === "ENRUTADO" || estado === "RESUELTO") return "marca";
  return "neutro";
}
