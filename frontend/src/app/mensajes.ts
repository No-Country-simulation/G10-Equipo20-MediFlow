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
  limite_render: "Las páginas escaneadas del PDF pesan demasiado para procesarlas.",
  pdf_tiempo_excedido: "La lectura del PDF tardó demasiado y se descartó. Revisa que el archivo no esté dañado.",
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
  destino_inactivo: "Destino sin uso en esta clínica",
  identidad_en_conflicto: "Documento de identidad registrado con otro nombre",
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

/** Hallazgos críticos del pack con su nombre clínico. Un concepto ampliado por el gestor se muestra legible igual. */
export const ETIQUETA_CONCEPTO: Record<string, string> = {
  TEP_AGUDO: "Tromboembolismo pulmonar agudo",
  IAM_STEMI: "Infarto con elevación del ST",
  DISECCION_AORTICA: "Disección aórtica",
  NEUMOTORAX_TENSION: "Neumotórax a tensión",
  TAPONAMIENTO_CARDIACO: "Taponamiento cardíaco",
  INSUF_RESPIRATORIA_AGUDA: "Insuficiencia respiratoria aguda",
  ARRITMIA_MALIGNA: "Arritmia maligna",
  EDEMA_AGUDO_PULMON: "Edema agudo de pulmón",
};

function legible(codigo: string): string {
  const texto = codigo.toLowerCase().replace(/_/g, " ").trim();
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

export function etiquetaConcepto(codigo: string | null | undefined): string {
  if (!codigo) return "";
  return ETIQUETA_CONCEPTO[codigo] ?? legible(codigo);
}

export function etiquetaEstado(codigo: string | null | undefined): string {
  if (!codigo) return "";
  return (ETIQUETA_ESTADO as Record<string, string>)[codigo] ?? legible(codigo);
}

const RESUMEN_MOTIVO: Record<string, string> = {
  fallo_tecnico: "El motor de extracción no respondió; el documento pasa a revisión manual.",
};

/**
 * Motivo de una transición para el clínico: una frase en español y, aparte, el detalle técnico
 * (excepciones, claves de configuración) para quien lo necesite.
 */
export function motivoLegible(texto: string | null | undefined): { resumen: string; tecnico: string | null } {
  if (!texto) return { resumen: "", tecnico: null };
  const separador = texto.indexOf(":");
  const codigo = (separador >= 0 ? texto.slice(0, separador) : texto).trim();
  if (codigo in MOTIVO_AUDITORIA) {
    const resto = separador >= 0 ? texto.slice(separador + 1).trim() : "";
    return { resumen: RESUMEN_MOTIVO[codigo] ?? `${etiquetaMotivo(codigo)}.`, tecnico: resto || null };
  }
  return { resumen: texto, tecnico: null };
}

export const ETIQUETA_DESTINO: Record<string, string> = {
  Cola_Emergencia_Medica: "Emergencia médica",
  Auditoria_Autorizaciones: "Auditoría de autorizaciones",
  Farmacia_Hospitalaria: "Farmacia",
  Historia_Clinica_Electronica: "Historia clínica",
  Cola_Revision_Humana: "Revisión humana",
  Gestion_Programa_Cobertura: "Programa de cobertura",
};

export function etiquetaDestino(codigo: string): string {
  return ETIQUETA_DESTINO[codigo] ?? legible(codigo);
}

/** Tipos de documento con la mayúscula del español ("No clasificable", no "No Clasificable"). El valor del backend no cambia. */
export const ETIQUETA_TIPO: Record<string, string> = {
  "Receta Médica": "Receta médica",
  "Informe de Imágenes": "Informe de imágenes",
  "Informe de Laboratorio": "Informe de laboratorio",
  "Orden de Procedimiento": "Orden de procedimiento",
  "Epicrisis o Alta": "Epicrisis o alta",
  "Certificado Médico": "Certificado médico",
  "No Clasificable": "No clasificable",
};

export function etiquetaTipo(tipo: string | null | undefined): string {
  if (!tipo) return "";
  return ETIQUETA_TIPO[tipo] ?? tipo;
}

/** Hallazgos de un caso en una línea; un concepto vacío se nombra en vez de mostrarse como "sin concepto". */
export function tituloHallazgos(conceptos: string[] | null | undefined): string {
  return (conceptos ?? []).map(etiquetaConcepto).join(" · ");
}
