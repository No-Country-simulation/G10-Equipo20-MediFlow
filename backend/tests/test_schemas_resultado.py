"""Paso 3: contrato de salida (JSON de resultado) del agente.

Se respeta el contrato del brief y solo se agregan campos (RN-G7), salvo las
dos desviaciones de la sección 1.3: alerta sin nombre del paciente (RN-Q4) y
nivel Crítico para el TEP (opción A de 2.2).
"""
import pytest
from pydantic import ValidationError

from app.schemas.resultado import (
    Destino,
    EstadoDocumento,
    MotivoAuditoria,
    NivelPrioridad,
    ResultadoTriaje,
    TipoDocumento,
)


def resultado_base() -> dict:
    """Caso 1 del brief: TC de tórax con TEP, sin identificador del paciente."""
    return {
        "documento_id": "DOC-CLIN-2026-8942",
        "clasificacion": {
            "tipo": "Informe de Imágenes",
            "setting": "urgencia",
            "especialidad": "Radiología",
            "dominio": "Neumología",
            "score_confianza": 0.97,
            "nivel_prioridad": "Crítico",
        },
        "extraccion": {
            "paciente": {
                "nome": "Carlos Eduardo Mendes",
                "edad": 52,
                "documento": {"tipo": "ausente", "valor": None, "estado": "ausente"},
            },
            "profesional": {
                "nombre_token": "PROF_001",
                "registro_profesional": "RM-45678",
                "tipo_documento": "CC",
            },
            "fecha_documento": "03/04/2026",
            "signos_vitales": {"FR": 28, "SpO2": 88, "FC": 118, "PAS": 92, "Temp": 37.1, "NEWS2_total": 10},
            "diagnosticos": [
                {"texto": "Tromboembolismo pulmonar agudo", "cie10_sugerido": "I26.9", "cie11_sugerido": "BB00.0"}
            ],
            "procedimientos": [{"texto": "TC de tórax con contraste", "cups": "879111"}],
            "medicamentos": [],
            "hallazgos_criticos_detectados": ["TEP_AGUDO"],
        },
        "evaluacion": {
            "requiere_auditoria_humana": False,
            "motivo_auditoria": None,
            "campos_dudosos": [],
        },
        "enrutamiento": {
            "destino_principal": "Cola_Emergencia_Medica",
            "destinos_secundarios": ["Historia_Clinica_Electronica"],
            "justificacion_enrutamiento": "Hallazgo crítico TEP_AGUDO (RN-D1); informe de imágenes crítico va a Emergencia + HCE (RN-E2).",
        },
        "notificacion_generada": {
            "canal": "Slack",
            "destinatario": "Jefe de Urgencias",
            "mensaje": "Alerta Crítica. Doc: DOC-CLIN-2026-8942. Nivel: Crítico. Requiere acuse.",
            "estado_acuse": "pendiente",
        },
    }


def test_resultado_del_caso_1_es_valido():
    r = ResultadoTriaje(**resultado_base())
    assert r.clasificacion.nivel_prioridad is NivelPrioridad.CRITICO
    assert r.enrutamiento.destino_principal is Destino.COLA_EMERGENCIA_MEDICA


def test_prioridad_tiene_tres_valores_opcion_A():
    assert {n.value for n in NivelPrioridad} == {"Crítico", "Urgente", "Rutina"}


def test_tipos_de_documento_son_lista_cerrada_RN_B1():
    assert {t.value for t in TipoDocumento} == {
        "Receta Médica", "Informe de Imágenes", "Informe de Laboratorio", "Orden de Procedimiento",
        "Epicrisis o Alta", "Certificado Médico", "No Clasificable",
    }


def test_destinos_incluyen_gestion_programa_cobertura_RN_E1():
    assert {d.value for d in Destino} == {
        "Cola_Emergencia_Medica", "Auditoria_Autorizaciones", "Farmacia_Hospitalaria",
        "Historia_Clinica_Electronica", "Cola_Revision_Humana", "Gestion_Programa_Cobertura",
    }


def test_nome_y_nombre_son_espejo_RN_G7():
    r = ResultadoTriaje(**resultado_base())
    assert r.extraccion.paciente.nombre == "Carlos Eduardo Mendes"
    assert r.extraccion.paciente.nome == "Carlos Eduardo Mendes"
    datos = resultado_base()
    datos["extraccion"]["paciente"] = {
        "nombre": "Ana Pérez",
        "edad": 30,
        "documento": {"tipo": "CC", "valor": "1020304050", "estado": "valido_formato"},
    }
    assert ResultadoTriaje(**datos).extraccion.paciente.nome == "Ana Pérez"


def test_nome_y_nombre_distintos_es_invalido_RN_G7():
    datos = resultado_base()
    datos["extraccion"]["paciente"]["nombre"] = "Otro Nombre"
    with pytest.raises(ValidationError):
        ResultadoTriaje(**datos)


def test_mensaje_de_alerta_no_lleva_nombre_del_paciente_RN_Q4():
    datos = resultado_base()
    datos["notificacion_generada"]["mensaje"] = "Alerta: Carlos Eduardo Mendes con TEP. Doc DOC-CLIN-2026-8942"
    with pytest.raises(ValidationError, match="RN-Q4"):
        ResultadoTriaje(**datos)


def test_mensaje_de_alerta_no_lleva_apellido_suelto_RN_Q4():
    datos = resultado_base()
    datos["notificacion_generada"]["mensaje"] = "Alerta Crítica paciente Mendes. Doc: DOC-CLIN-2026-8942"
    with pytest.raises(ValidationError, match="RN-Q4"):
        ResultadoTriaje(**datos)


def test_mensaje_de_alerta_no_lleva_documento_del_paciente_RN_Q4():
    datos = resultado_base()
    datos["extraccion"]["paciente"]["documento"] = {"tipo": "CC", "valor": "1020304050", "estado": "valido_formato"}
    datos["notificacion_generada"]["mensaje"] = "Alerta Crítica. CC 1020304050. Doc: DOC-CLIN-2026-8942"
    with pytest.raises(ValidationError, match="RN-Q4"):
        ResultadoTriaje(**datos)


def test_critico_sin_notificacion_es_invalido_RN_F1():
    datos = resultado_base()
    datos["notificacion_generada"] = None
    with pytest.raises(ValidationError, match="RN-F1"):
        ResultadoTriaje(**datos)


def test_notificacion_nace_con_acuse_pendiente_y_fecha_RN_F1():
    r = ResultadoTriaje(**resultado_base())
    assert r.notificacion_generada.estado_acuse == "pendiente"
    assert r.notificacion_generada.fecha_hora is not None


def test_rutina_sin_notificacion_es_valido_RN_Q3():
    datos = resultado_base()
    datos["clasificacion"]["nivel_prioridad"] = "Rutina"
    datos["extraccion"]["hallazgos_criticos_detectados"] = []
    datos["notificacion_generada"] = None
    datos["enrutamiento"]["destino_principal"] = "Historia_Clinica_Electronica"
    datos["enrutamiento"]["destinos_secundarios"] = []
    assert ResultadoTriaje(**datos).notificacion_generada is None


def test_hallazgo_critico_con_prioridad_menor_es_invalido_RN_D8():
    datos = resultado_base()
    datos["clasificacion"]["nivel_prioridad"] = "Urgente"
    with pytest.raises(ValidationError, match="RN-D8"):
        ResultadoTriaje(**datos)


def test_auditoria_humana_exige_motivo_cerrado_RN_C1():
    datos = resultado_base()
    datos["evaluacion"] = {"requiere_auditoria_humana": True, "motivo_auditoria": None, "campos_dudosos": ["dosis"]}
    datos["enrutamiento"]["destino_principal"] = "Cola_Revision_Humana"
    with pytest.raises(ValidationError):
        ResultadoTriaje(**datos)
    datos["evaluacion"]["motivo_auditoria"] = "porque_si"
    with pytest.raises(ValidationError):
        ResultadoTriaje(**datos)
    datos["evaluacion"]["motivo_auditoria"] = "receta_incompleta_norma"
    assert ResultadoTriaje(**datos).evaluacion.motivo_auditoria is MotivoAuditoria.RECETA_INCOMPLETA_NORMA


def test_motivos_de_auditoria_del_docx_existen():
    esperados = {
        "receta_incompleta_norma", "control_especial_sin_recetario", "cobertura_no_informada",
        "cobertura_no_configurada", "fuera_de_alcance", "fallo_tecnico", "documentacion_incompleta",
        "clasificacion_baja_confianza", "no_clasificable", "campo_dudoso", "ambiguo", "ilegible",
        "dosis_ambigua", "fecha_ambigua", "identidad_invalida", "profesional_no_identificable",
        "signos_vitales_sin_escala", "critico_baja_confianza",
    }
    assert esperados <= {m.value for m in MotivoAuditoria}


def test_sin_auditoria_no_puede_haber_motivo():
    datos = resultado_base()
    datos["evaluacion"]["motivo_auditoria"] = "ambiguo"
    with pytest.raises(ValidationError):
        ResultadoTriaje(**datos)


def test_auditoria_humana_enruta_a_cola_de_revision_RN_E8():
    datos = resultado_base()
    datos["evaluacion"] = {"requiere_auditoria_humana": True, "motivo_auditoria": "ambiguo", "campos_dudosos": []}
    with pytest.raises(ValidationError, match="RN-E8"):
        ResultadoTriaje(**datos)
    datos["enrutamiento"]["destino_principal"] = "Cola_Revision_Humana"
    r = ResultadoTriaje(**datos)
    # RN-D9: el crítico con revisión humana conserva su alerta
    assert r.notificacion_generada is not None


def test_destino_principal_no_se_repite_en_secundarios_RN_E3():
    datos = resultado_base()
    datos["enrutamiento"]["destinos_secundarios"] = ["Cola_Emergencia_Medica"]
    with pytest.raises(ValidationError, match="RN-E3"):
        ResultadoTriaje(**datos)


def test_score_confianza_entre_0_y_1():
    datos = resultado_base()
    datos["clasificacion"]["score_confianza"] = 1.2
    with pytest.raises(ValidationError):
        ResultadoTriaje(**datos)


def test_registra_pack_y_version_de_reglas_RN_G6():
    r = ResultadoTriaje(**resultado_base())
    assert r.pack_pais == "CO"
    assert r.version_reglas == "8"


def test_historial_de_decisiones_RN_G2():
    datos = resultado_base()
    datos["historial_decisiones"] = [{
        "regla": "RN-D8",
        "evidencia": "cie10_sugerido=I26.9",
        "propuesta_llm": "Rutina",
        "decision": "Crítico",
    }]
    r = ResultadoTriaje(**datos)
    assert r.historial_decisiones[0].regla == "RN-D8"
    assert r.historial_decisiones[0].fecha_hora is not None


def test_estado_del_ciclo_de_vida_es_cerrado_RN_I1():
    assert {e.value for e in EstadoDocumento} == {
        "RECIBIDO", "VALIDADO", "CLASIFICADO", "EXTRAIDO", "EVALUADO", "EN_REVISION_HUMANA",
        "RESUELTO", "ENRUTADO", "ENTREGADO", "RECHAZADO", "FALLO_TECNICO",
    }
    r = ResultadoTriaje(**resultado_base())
    assert r.estado is EstadoDocumento.EVALUADO


def test_status_backup_por_defecto_pendiente_RN_G3():
    r = ResultadoTriaje(**resultado_base())
    assert r.status_backup == "pendiente"
    assert r.ruta_storage is None


def test_fecha_documento_respeta_dd_mm_aaaa_RN_CO11():
    datos = resultado_base()
    datos["extraccion"]["fecha_documento"] = "2026-04-03"
    with pytest.raises(ValidationError):
        ResultadoTriaje(**datos)


def test_json_schema_se_exporta_para_el_brief():
    esquema = ResultadoTriaje.model_json_schema()
    assert "documento_id" in esquema["properties"]
    assert "notificacion_generada" in esquema["properties"]


def test_serializacion_conserva_nombres_del_brief_RN_G7():
    salida = ResultadoTriaje(**resultado_base()).model_dump(mode="json")
    for campo in ("documento_id", "clasificacion", "extraccion", "evaluacion", "enrutamiento", "notificacion_generada"):
        assert campo in salida
    assert salida["extraccion"]["paciente"]["nome"] == salida["extraccion"]["paciente"]["nombre"]
    assert salida["clasificacion"]["nivel_prioridad"] == "Crítico"
