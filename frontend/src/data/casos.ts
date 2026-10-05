/** Casos de prueba sintéticos (RN-CO19: ningún dato real). Espejo de samples/ en el repo. */
import type { CanalOrigen, Cobertura } from "../types";

export interface CasoPrueba {
  id: string;
  nombre: string;
  descripcion: string;
  documento_id: string;
  canal_origen: CanalOrigen;
  cobertura_paciente?: Cobertura;
  texto: string;
}

export const CASOS: CasoPrueba[] = [
  {
    id: "tep-masivo-c1",
    nombre: "TEP Masivo C1",
    descripcion: "Caso 1 del brief: TC de tórax con TEP, sin identificador del paciente. Esperado: Crítico, Emergencia + HCE retenida.",
    documento_id: "DOC-CLIN-2026-8942",
    canal_origen: "Guardia_Emergencias",
    texto: `INFORME DE TOMOGRAFÍA COMPUTARIZADA DE TÓRAX CON CONTRASTE
IPS Cardiovida - Servicio de Urgencias
Fecha: 03/04/2026

Paciente: Carlos Eduardo Mendes, 52 años, masculino.
Motivo: disnea súbita y dolor torácico pleurítico de 6 horas de evolución.
Signos vitales al ingreso: FR 28, SpO2 88 %, FC 118, PAS 92, Temp 37,1 °C. Alerta.

HALLAZGOS: defectos de llenado en ambas arterias pulmonares principales con extensión lobar.
Dilatación del ventrículo derecho (relación VD/VI 1,4). Sin derrame pleural significativo.

CONCLUSIÓN: tromboembolismo pulmonar agudo bilateral con signos de sobrecarga de VD. CIE-10 I26.9.

Dr. Andrés Felipe Rojas, radiólogo. RM 45678.`,
  },
  {
    id: "apixaban",
    nombre: "Fórmula con Apixabán",
    descripcion: "Caso 3: anticoagulante de alto riesgo. Esperado: Farmacia con alto_riesgo y doble verificación.",
    documento_id: "DOC-REC-2026-0311",
    canal_origen: "Consulta_Ambulatoria",
    cobertura_paciente: "contributivo",
    texto: `FÓRMULA MÉDICA
IPS Cardiovida - Consulta externa de Cardiología
Fecha: 03/04/2026

Paciente: Jorge Luis Ramírez Ortiz, 71 años. CC 19.345.678
Diagnóstico: fibrilación auricular no valvular (I48.0), CHA2DS2-VASc 4.

Medicamento: Apixabán 5 mg tableta. Vía oral. Dosis: 1 tableta cada 12 horas.
Duración: 30 días. Cantidad total: 60 (sesenta) tabletas.

Dra. Carolina Duque Ramírez, cardióloga. RM 78901.`,
  },
  {
    id: "losartan",
    nombre: "Fórmula de Losartán",
    descripcion: "Caso 2 del brief: fórmula de mantenimiento completa. Esperado: Rutina, Farmacia.",
    documento_id: "DOC-REC-2026-0302",
    canal_origen: "Consulta_Ambulatoria",
    cobertura_paciente: "contributivo",
    texto: `FÓRMULA MÉDICA
IPS Cardiovida - Consulta externa de Cardiología. NIT 800.197.268-4
Fecha: 03/04/2026

Paciente: Ana María Pérez Gómez, 58 años. CC 41.234.567
Diagnóstico: hipertensión arterial esencial (I10)

Medicamento: Losartán potásico 50 mg tableta. Vía oral. Dosis: 1 tableta cada 24 horas.
Duración: 30 días. Cantidad total: 30 (treinta) tabletas.

Dra. Carolina Duque Ramírez, cardióloga. RM 78901.`,
  },
  {
    id: "cc-invalida",
    nombre: "Laboratorio con CC inválida",
    descripcion: "Caso 6 del brief: identificador con formato inválido. Esperado: revisión humana con campos dudosos.",
    documento_id: "DOC-LAB-2026-0406",
    canal_origen: "Consulta_Ambulatoria",
    texto: `INFORME DE LABORATORIO
Laboratorio Clínico Cardiovida. Fecha: 03/04/2026
Paciente: Pedro Gómez, 45 años. CC 12AB45
Estudio: perfil lipídico. Colesterol total 245 mg/dL, LDL 160 mg/dL, HDL 38 mg/dL, triglicéridos 210 mg/dL.
Conclusión: dislipidemia mixta (E78.2).
Bacterióloga: Sandra Molina. TP 4471.`,
  },
];
