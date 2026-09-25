"""Paso 9: enrutamiento (RN-E), notificación (RN-F, RN-Q) y JSON final.

Cubre los casos de aceptación 1, 2, 3, 4, 5, 7, 23, 24 y 25.
"""
import pytest

from app.packs.loader import cargar_pack, cargar_umbrales
from app.schemas.resultado import Destino as D, EstadoDocumento as E, MotivoAuditoria as M, NivelPrioridad as N, ResultadoTriaje
from app.services.enrutamiento import ContextoEnrutamiento, enrutar
from app.services.evaluacion import evaluar
from tests.fabrica import ctx, med, orden, propuesta, receta, tep

PACK = cargar_pack("CO")
UMB = cargar_umbrales()


def procesar(p, *, canal="Consulta_Ambulatoria", cobertura=None, texto="Texto clínico.", documento_id="DOC-CLIN-2026-8942") -> ResultadoTriaje:
    evaluado = evaluar(p, ctx(canal_origen=canal, cobertura_request=cobertura, texto=texto), PACK, UMB)
    contexto = ContextoEnrutamiento(documento_id=documento_id, canal_origen=canal, pais="CO", version=1, url_base="https://mediflow.local/documentos")
    return enrutar(evaluado, contexto, PACK, UMB)


# --- Caso 1: el ejemplo del brief ---------------------------------------------------


def test_caso_1_TEP_sin_id_es_critico_a_emergencia_mas_HCE_sin_revision_humana():
    r = procesar(tep(), canal="Guardia_Emergencias")
    assert isinstance(r, ResultadoTriaje)
    assert r.clasificacion.nivel_prioridad is N.CRITICO
    assert r.enrutamiento.destino_principal is D.COLA_EMERGENCIA_MEDICA
    assert r.enrutamiento.destinos_secundarios == [D.HISTORIA_CLINICA_ELECTRONICA]
    assert r.evaluacion.requiere_auditoria_humana is False
    assert r.evaluacion.motivo_auditoria is None
    assert r.extraccion.paciente.documento.estado == "ausente"


def test_caso_1_la_alerta_no_lleva_datos_del_paciente_RN_Q4_RN_F1():
    r = procesar(tep(), canal="Guardia_Emergencias")
    n = r.notificacion_generada
    assert n is not None
    assert n.mensaje == "Alerta Crítica. Doc: DOC-CLIN-2026-8942. Nivel: Crítico. Requiere acuse."
    assert n.estado_acuse == "pendiente"
    assert n.destinatario == "Jefe de Urgencias"
    assert n.enlace == "https://mediflow.local/documentos/DOC-CLIN-2026-8942"
    assert "Mendes" not in n.mensaje


def test_caso_1_sin_identificador_retiene_la_entrega_a_HCE_RN_A4():
    r = procesar(tep(), canal="Guardia_Emergencias")
    assert r.enrutamiento.entregas_retenidas == {"Historia_Clinica_Electronica": "identidad_ausente_conciliar"}


def test_caso_1_ruta_en_procesados_criticos_RN_G1():
    r = procesar(tep(), canal="Guardia_Emergencias")
    assert r.ruta_storage == "co/procesados/criticos/DOC-CLIN-2026-8942.json"
    assert r.estado is E.ENRUTADO


def test_caso_1_JSON_respeta_los_nombres_del_brief_y_lleva_trazabilidad_RN_G2_RN_G6_RN_G7():
    salida = procesar(tep(), canal="Guardia_Emergencias").model_dump(mode="json")
    for campo in ("documento_id", "clasificacion", "extraccion", "evaluacion", "enrutamiento", "notificacion_generada"):
        assert campo in salida
    assert salida["extraccion"]["paciente"]["nome"] == "Carlos Eduardo Mendes"
    assert salida["extraccion"]["signos_vitales"]["NEWS2_total"] == 10
    assert salida["pack_pais"] == "CO" and salida["version_reglas"] == "8"
    reglas = {h["regla"] for h in salida["historial_decisiones"]}
    assert {"RN-D2", "RN-E2", "RN-F1"} <= reglas


# --- Recetas -------------------------------------------------------------------------


def test_caso_2_receta_completa_es_rutina_a_farmacia_RN_E2():
    r = procesar(receta([med()]))
    assert r.clasificacion.nivel_prioridad is N.RUTINA
    assert r.enrutamiento.destino_principal is D.FARMACIA_HOSPITALARIA
    assert r.notificacion_generada is None  # RN-Q3: rutina no notifica
    assert r.ruta_storage == "co/procesados/rutina/DOC-CLIN-2026-8942.json"


def test_caso_3_apixaban_va_a_farmacia_con_alto_riesgo_y_doble_verificacion_RN_E6_RN_J6():
    r = procesar(receta([med("apixaban", dosis="5 mg")]))
    assert r.enrutamiento.destino_principal is D.FARMACIA_HOSPITALARIA
    assert r.extraccion.medicamentos[0].alto_riesgo is True
    assert "doble verificación" in r.enrutamiento.justificacion_enrutamiento
    assert r.evaluacion.requiere_auditoria_humana is False


def test_receta_critica_va_a_farmacia_prioritaria_con_emergencia_RN_E2():
    r = procesar(receta([med("heparina", dosis="5.000 UI", via="IV")], **{"clasificacion.nivel_prioridad_propuesto": "Crítico"}),
                 texto="Heparina 5.000 UI IV. Losartán 0,5 mg.")
    assert r.enrutamiento.destino_principal is D.FARMACIA_HOSPITALARIA
    assert D.COLA_EMERGENCIA_MEDICA in r.enrutamiento.destinos_secundarios
    assert r.notificacion_generada is not None


def test_mipres_queda_no_evaluado_mientras_la_lista_este_por_confirmar_RN_CO14():
    r = procesar(receta([med()]))
    assert D.GESTION_PROGRAMA_COBERTURA not in r.enrutamiento.destinos_secundarios
    assert any(h.regla == "RN-CO14" and "mipres_no_evaluado" in h.decision for h in r.historial_decisiones)


# --- Órdenes de procedimiento ----------------------------------------------------------


def test_caso_5_cateterismo_desde_urgencias_a_emergencia_sin_autorizacion_RN_E4_RN_CO13():
    r = procesar(orden(), canal="Guardia_Emergencias")
    assert r.enrutamiento.destino_principal is D.COLA_EMERGENCIA_MEDICA
    assert r.enrutamiento.destinos_secundarios == [D.AUDITORIA_AUTORIZACIONES]
    assert r.enrutamiento.motivos_destino["Auditoria_Autorizaciones"] == "informe_atencion_inicial_urgencias"
    assert r.evaluacion.requiere_auditoria_humana is False


def test_hospitalizado_tampoco_espera_autorizacion_RN_CO13():
    r = procesar(orden(), canal="Hospitalizado")
    assert r.enrutamiento.destino_principal is D.COLA_EMERGENCIA_MEDICA


def test_caso_23_orden_ambulatoria_contributivo_completa_a_auditoria_con_solicitud_a_EPS_RN_E9_RN_CO12():
    r = procesar(orden(), cobertura="contributivo")
    assert r.enrutamiento.destino_principal is D.AUDITORIA_AUTORIZACIONES
    assert r.enrutamiento.motivos_destino["Auditoria_Autorizaciones"] == "solicitud_autorizacion_eps"
    assert r.enrutamiento.documentacion_incompleta is False
    assert r.evaluacion.requiere_auditoria_humana is False


def test_caso_4_orden_sin_justificacion_es_documentacion_incompleta_RN_E5():
    r = procesar(orden(procedimiento="Ecocardiograma de estrés", cups="880202", justificacion=None), cobertura="contributivo")
    assert r.enrutamiento.destino_principal is D.AUDITORIA_AUTORIZACIONES
    assert r.enrutamiento.documentacion_incompleta is True
    assert r.enrutamiento.motivos_destino["Auditoria_Autorizaciones"] == "documentacion_incompleta"
    assert r.evaluacion.requiere_auditoria_humana is False


def test_orden_sin_CUPS_es_documentacion_incompleta_RN_CO7():
    r = procesar(orden(cups=None), cobertura="contributivo")
    assert r.enrutamiento.documentacion_incompleta is True


def test_caso_24_orden_sin_cobertura_va_a_revision_humana_RN_E10():
    r = procesar(orden())
    assert r.evaluacion.requiere_auditoria_humana is True
    assert r.evaluacion.motivo_auditoria is M.COBERTURA_NO_INFORMADA
    assert r.enrutamiento.destino_principal is D.COLA_REVISION_HUMANA
    assert r.enrutamiento.destinos_tras_revision == [D.AUDITORIA_AUTORIZACIONES]
    assert r.ruta_storage == "co/auditoria_humana/DOC-CLIN-2026-8942.json"
    assert r.estado is E.EN_REVISION_HUMANA


def test_cobertura_detectada_en_el_documento_sirve_si_el_request_no_la_trae_RN_A10():
    r = procesar(orden(**{"extraccion.cobertura_detectada": "subsidiado"}))
    assert r.enrutamiento.destino_principal is D.AUDITORIA_AUTORIZACIONES


def test_caso_25_cobertura_especial_excepcion_va_a_revision_RN_E11():
    r = procesar(orden(), cobertura="especial_excepcion")
    assert r.evaluacion.motivo_auditoria is M.COBERTURA_NO_CONFIGURADA


def test_orden_critica_ambulatoria_va_a_emergencia_sin_autorizacion_RN_E2():
    r = procesar(orden(**{"extraccion.diagnosticos": [{"texto": "IAM STEMI", "cie10_sugerido": "I21.0", "cie11_sugerido": None}]}), cobertura="contributivo")
    assert r.clasificacion.nivel_prioridad is N.CRITICO
    assert r.enrutamiento.destino_principal is D.COLA_EMERGENCIA_MEDICA


def test_orden_urgente_es_via_rapida_en_auditoria_RN_E2():
    r = procesar(orden(**{"clasificacion.nivel_prioridad_propuesto": "Urgente"}), cobertura="contributivo")
    assert r.enrutamiento.destino_principal is D.AUDITORIA_AUTORIZACIONES
    assert r.enrutamiento.motivos_destino["Auditoria_Autorizaciones"] == "via_rapida"
    assert r.notificacion_generada is not None  # RN-F3: aviso al solicitante
    assert r.notificacion_generada.destinatario == "Profesional solicitante"


# --- Epicrisis, certificados e informes --------------------------------------------------


def test_caso_7_epicrisis_de_IAM_con_revascularizacion_va_a_HCE_con_alto_costo_inactivo_RN_E7_RN_CO15():
    p = propuesta(**{
        "clasificacion.tipo": "Epicrisis o Alta", "clasificacion.setting": "hospitalizado",
        "extraccion.diagnosticos": [{"texto": "IAM, revascularización quirúrgica", "cie10_sugerido": "I21.9", "cie11_sugerido": None}],
        "extraccion.procedimientos": [{"texto": "Revascularización miocárdica", "cups": "361100"}],
    })
    r = procesar(p, canal="Hospitalizado")
    assert r.enrutamiento.destino_principal is D.HISTORIA_CLINICA_ELECTRONICA
    assert D.GESTION_PROGRAMA_COBERTURA not in r.enrutamiento.destinos_secundarios
    assert any(h.regla == "RN-CO15" for h in r.historial_decisiones)


def test_epicrisis_critica_agrega_emergencia_RN_E2():
    p = propuesta(**{"clasificacion.tipo": "Epicrisis o Alta",
                     "extraccion.diagnosticos": [{"texto": "TEP", "cie10_sugerido": "I26.9", "cie11_sugerido": None}]})
    r = procesar(p, canal="Hospitalizado")
    assert r.enrutamiento.destino_principal is D.HISTORIA_CLINICA_ELECTRONICA
    assert D.COLA_EMERGENCIA_MEDICA in r.enrutamiento.destinos_secundarios


def test_certificado_siempre_a_HCE():
    p = propuesta(**{"clasificacion.tipo": "Certificado Médico", "clasificacion.dominio": "Otro", "extraccion.procedimientos": []})
    r = procesar(p)
    assert r.enrutamiento.destino_principal is D.HISTORIA_CLINICA_ELECTRONICA


def test_informe_rutina_a_HCE_e_informe_urgente_avisa_al_solicitante_RN_E2_RN_F3():
    assert procesar(propuesta()).enrutamiento.destino_principal is D.HISTORIA_CLINICA_ELECTRONICA
    r = procesar(propuesta(**{"clasificacion.nivel_prioridad_propuesto": "Urgente"}))
    assert r.enrutamiento.destino_principal is D.HISTORIA_CLINICA_ELECTRONICA
    assert r.notificacion_generada.destinatario == "Profesional solicitante"


# --- Revisión humana y alerta ---------------------------------------------------------------


def test_revision_humana_manda_a_la_cola_y_guarda_el_plan_RN_E8():
    r = procesar(receta([med(cantidad_letras=None)]))
    assert r.enrutamiento.destino_principal is D.COLA_REVISION_HUMANA
    assert r.enrutamiento.destinos_secundarios == []
    assert r.enrutamiento.destinos_tras_revision == [D.FARMACIA_HOSPITALARIA]


def test_critico_con_baja_confianza_alerta_aunque_vaya_a_revision_RN_D9():
    r = procesar(tep(**{"confianzas.diagnostico_codigo": 0.5}), canal="Guardia_Emergencias")
    assert r.enrutamiento.destino_principal is D.COLA_REVISION_HUMANA
    assert r.notificacion_generada is not None
    assert r.notificacion_generada.mensaje.startswith("Alerta Crítica")


@pytest.mark.parametrize("nivel, carpeta", [("Crítico", "criticos"), ("Urgente", "urgentes"), ("Rutina", "rutina")])
def test_ruta_de_procesados_por_nivel_RN_G1(nivel, carpeta):
    r = procesar(propuesta(**{"clasificacion.nivel_prioridad_propuesto": nivel}))
    assert r.ruta_storage == f"co/procesados/{carpeta}/DOC-CLIN-2026-8942.json"


def test_version_2_lleva_sufijo_en_la_ruta_RN_O2():
    evaluado = evaluar(propuesta(), ctx(), PACK, UMB)
    r = enrutar(evaluado, ContextoEnrutamiento(documento_id="DOC-X", canal_origen="Externo", pais="CO", version=2, url_base="http://x"), PACK, UMB)
    assert r.ruta_storage == "co/procesados/rutina/DOC-X_v2.json"
