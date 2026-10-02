"""Paso 10: grafo LangGraph que une los nodos con los estados de la sección 3.

Pipeline: VALIDADO -> CLASIFICADO -> EXTRAIDO -> EVALUADO -> ENRUTADO | EN_REVISION_HUMANA.
Ruta de fallo (RN-P2, RN-P4): con el LLM caído, la detección determinística sigue
alertando sobre texto y el documento va a revisión humana con motivo fallo_tecnico.
"""
import pytest

from app.models.documento import Documento
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.request import DocumentoRequest
from app.schemas.resultado import EstadoDocumento as E, MotivoAuditoria as M
from app.services.ingesta import ServicioIngesta
from app.services.llm import ClienteFalso, ErrorTransitorioLLM, ServicioExtraccion
from app.services.orquestador import Orquestador
from tests.test_llm import propuesta_caso_1

TEXTO_CASO_1 = (
    "Paciente: Carlos Eduardo Mendes, 52 años. Fecha: 03/04/2026.\n"
    "TC de tórax con contraste: tromboembolismo pulmonar agudo bilateral. FR 28, SpO2 88 %, FC 118, PAS 92.\n"
    "Dr. Andrés Rojas, RM 45678."
)


def request_caso_1(**extra) -> DocumentoRequest:
    datos = {"documento_id": "DOC-CLIN-2026-8942", "canal_origen": "Guardia_Emergencias", "tipo_contenido": "texto",
             "contenido_texto": TEXTO_CASO_1}
    datos.update(extra)
    return DocumentoRequest(**datos)


@pytest.fixture
def repo(session):
    return RepositorioDocumentos(session)


def orquestador(repo, storage, cliente_llm, **kw) -> Orquestador:
    return Orquestador(repo, storage, ServicioExtraccion(cliente_llm, max_intentos=2, espera_base_s=0, dormir=lambda s: None), **kw)


def ingresar(repo, storage, request=None) -> Documento:
    return ServicioIngesta(repo, storage).recibir(request or request_caso_1()).documento


# --- Camino feliz: caso 1 de punta a punta ----------------------------------------------


def test_caso_1_de_punta_a_punta(repo, storage):
    cliente = ClienteFalso(respuestas=[propuesta_caso_1()], tokens=(1000, 300), modelo="falso")
    doc = ingresar(repo, storage)
    resultado = orquestador(repo, storage, cliente).procesar(doc)

    assert resultado.clasificacion.nivel_prioridad == "Crítico"
    assert resultado.enrutamiento.destino_principal == "Cola_Emergencia_Medica"
    assert resultado.evaluacion.requiere_auditoria_humana is False
    assert resultado.notificacion_generada.mensaje == "Alerta Crítica. Doc: DOC-CLIN-2026-8942. Nivel: Crítico. Requiere acuse."
    # Re-identificación: el JSON final lleva el nombre real, el LLM solo vio el token
    assert resultado.extraccion.paciente.nombre == "Carlos Eduardo Mendes"
    assert "Mendes" not in cliente.llamadas[0].texto_usuario
    assert resultado.extraccion.fecha_documento == "03/04/2026"


def test_caso_1_recorre_todos_los_estados_sin_saltar_etapas_RN_I2(repo, storage):
    doc = ingresar(repo, storage)
    orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()])).procesar(doc)
    estados = [t.a_estado for t in doc.transiciones]
    assert estados == [E.RECIBIDO, E.VALIDADO, E.CLASIFICADO, E.EXTRAIDO, E.EVALUADO, E.ENRUTADO]
    assert doc.estado == E.ENRUTADO
    assert doc.nivel_prioridad == "Crítico"


def test_resultado_se_persiste_y_se_respalda_en_procesados_criticos_RN_G1_RN_G2(repo, storage):
    doc = ingresar(repo, storage)
    r = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()])).procesar(doc)
    assert doc.resultado_json["documento_id"] == "DOC-CLIN-2026-8942"
    assert r.status_backup == "ok"
    assert r.ruta_storage == "co/procesados/criticos/DOC-CLIN-2026-8942.json"
    assert b'"historial_decisiones"' in storage.leer(r.ruta_storage)


def test_trazabilidad_de_modelo_prompt_y_tokens_RN_R5_RN_T3(repo, storage):
    doc = ingresar(repo, storage)
    orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()], tokens=(1000, 300), modelo="falso-1")).procesar(doc)
    assert doc.modelo_llm == "falso-1"
    assert doc.version_prompt.startswith("triaje_v")
    assert (doc.tokens_entrada, doc.tokens_salida) == (1000, 300)


def test_alerta_critica_queda_registrada_con_acuse_pendiente_RN_F1_RN_Q1(repo, storage):
    doc = ingresar(repo, storage)
    orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()])).procesar(doc)
    alerta = repo.alerta_activa(doc)
    assert alerta is not None
    assert alerta.nivel == "Crítico"
    assert alerta.estado_acuse == "pendiente"
    assert "Mendes" not in alerta.mensaje


def test_revision_humana_deja_el_documento_en_la_cola_RN_E8(repo, storage):
    p = propuesta_caso_1()
    p["confianzas"]["diagnostico_codigo"] = 0.5  # RN-D9
    doc = ingresar(repo, storage)
    r = orquestador(repo, storage, ClienteFalso(respuestas=[p])).procesar(doc)
    assert doc.estado == E.EN_REVISION_HUMANA
    assert r.enrutamiento.destino_principal == "Cola_Revision_Humana"
    assert r.ruta_storage == "co/auditoria_humana/DOC-CLIN-2026-8942.json"
    assert repo.alerta_activa(doc) is not None  # RN-D9: la alerta no espera a la revisión


# --- Fallo técnico (RN-P2, RN-P3, RN-P4) ------------------------------------------------------


def test_LLM_caido_con_TEP_en_el_texto_alerta_y_va_a_revision_RN_P4(repo, storage):
    cliente = ClienteFalso(respuestas=[ErrorTransitorioLLM("caído")] * 2)
    doc = ingresar(repo, storage)
    r = orquestador(repo, storage, cliente).procesar(doc)
    assert doc.estado == E.EN_REVISION_HUMANA
    assert r.evaluacion.motivo_auditoria is M.FALLO_TECNICO
    assert r.clasificacion.nivel_prioridad == "Crítico"
    assert "TEP_AGUDO" in r.extraccion.hallazgos_criticos_detectados
    assert r.notificacion_generada is not None
    assert repo.alerta_activa(doc).nivel == "Crítico"
    assert [t.a_estado for t in doc.transiciones][-2:] == [E.FALLO_TECNICO, E.EN_REVISION_HUMANA]


def test_LLM_caido_sin_hallazgos_va_a_revision_sin_alerta_RN_P2(repo, storage):
    cliente = ClienteFalso(respuestas=[ErrorTransitorioLLM("caído")] * 2)
    doc = ingresar(repo, storage, DocumentoRequest(documento_id="DOC-RUT", canal_origen="Externo", tipo_contenido="texto",
                                                   contenido_texto="Control de hipertensión. Losartán 50 mg."))
    r = orquestador(repo, storage, cliente).procesar(doc)
    assert doc.estado == E.EN_REVISION_HUMANA
    assert r.clasificacion.nivel_prioridad == "Rutina"
    assert r.notificacion_generada is None


def test_LLM_caido_la_prioridad_que_declara_el_documento_ordena_la_cola_RN_D8(repo, storage):
    cliente = ClienteFalso(respuestas=[ErrorTransitorioLLM("caído")] * 4)
    urgente = ingresar(repo, storage, DocumentoRequest(documento_id="DOC-URG", canal_origen="Externo", tipo_contenido="texto",
                                                       contenido_texto="Control de falla cardíaca.\nPrioridad: Urgente\nFurosemida 40 mg."))
    rutina = ingresar(repo, storage, DocumentoRequest(documento_id="DOC-RUT", canal_origen="Externo", tipo_contenido="texto",
                                                      contenido_texto="Control de hipertensión. Losartán 50 mg."))
    orq = orquestador(repo, storage, cliente)
    orq.procesar(rutina)
    r = orq.procesar(urgente)
    assert r.clasificacion.nivel_prioridad == "Urgente"
    assert r.notificacion_generada is None  # solo un Crítico alerta (RN-F1)
    assert any(d.regla == "RN-D8" and "Prioridad: Urgente" in d.evidencia for d in r.historial_decisiones)
    assert [d.documento_id for d in repo.en_revision()] == ["DOC-URG", "DOC-RUT"]  # RN-J1: por prioridad, no por llegada


def test_LLM_caido_un_critico_declarado_alerta_RN_F1(repo, storage):
    cliente = ClienteFalso(respuestas=[ErrorTransitorioLLM("caído")] * 2)
    doc = ingresar(repo, storage, DocumentoRequest(documento_id="DOC-CRI", canal_origen="Externo", tipo_contenido="texto",
                                                   contenido_texto="Informe de laboratorio.\nPrioridad clínica: crítica\nPotasio 6,9 mEq/L."))
    r = orquestador(repo, storage, cliente).procesar(doc)
    assert r.clasificacion.nivel_prioridad == "Crítico"
    assert repo.alerta_activa(doc).estado_acuse == "pendiente"


def test_imagen_con_LLM_caido_va_a_revision_con_prioridad_maxima_RN_P4(repo, storage):
    import base64
    from pathlib import Path

    png = (Path(__file__).resolve().parents[2] / "samples" / "archivos" / "cardio_scan.png").read_bytes()
    cliente = ClienteFalso(respuestas=[ErrorTransitorioLLM("caído")] * 2)
    doc = ingresar(repo, storage, DocumentoRequest(documento_id="DOC-IMG", canal_origen="Externo", tipo_contenido="imagen",
                                                   archivo_base64=base64.b64encode(png).decode(), nombre_archivo="cardio_scan.png"))
    r = orquestador(repo, storage, cliente).procesar(doc)
    assert doc.estado == E.EN_REVISION_HUMANA
    assert r.clasificacion.nivel_prioridad == "Crítico"
    assert r.evaluacion.motivo_auditoria is M.FALLO_TECNICO


def test_pdf_escaneado_manda_sus_paginas_como_imagenes_al_LLM_RN_M2(repo, storage):
    from pathlib import Path

    pdf = (Path(__file__).resolve().parents[2] / "samples" / "archivos" / "cardio_mixed.pdf").read_bytes()
    cliente = ClienteFalso(respuestas=[propuesta_caso_1()])
    doc = ServicioIngesta(repo, storage).recibir_archivo("cardio_mixed.pdf", pdf, documento_id="DOC-MIX", canal_origen="Externo").documento
    orquestador(repo, storage, cliente).procesar(doc)
    llamada = cliente.llamadas[0]
    assert "ECOCARDIOGRAMA" in llamada.texto_usuario
    assert len(llamada.imagenes) == 1 and llamada.imagenes[0][1] == "image/png"


def test_respuesta_fuera_de_esquema_es_fallo_tecnico_RN_P3(repo, storage):
    cliente = ClienteFalso(respuestas=[{"clasificacion": {"tipo": "Receta Médica"}}])
    doc = ingresar(repo, storage)
    r = orquestador(repo, storage, cliente).procesar(doc)
    assert r.evaluacion.motivo_auditoria is M.FALLO_TECNICO
    assert len(cliente.llamadas) == 1


# --- Validación dentro del grafo (sección 3.3, RN-I5) ---------------------------------------------


def test_el_grafo_recibe_en_RECIBIDO_valida_sin_LLM_y_rechaza_con_codigo_RN_I5_RN_A1(repo, storage):
    cliente = ClienteFalso(respuestas=[propuesta_caso_1()])
    doc = ingresar(repo, storage, request_caso_1(tipo_contenido="pdf", contenido_texto=None, archivo_base64="no-es-base64!!"))
    assert doc.estado == E.RECIBIDO
    r = orquestador(repo, storage, cliente).procesar(doc)
    assert r is None
    assert doc.estado == E.RECHAZADO
    assert doc.codigo_error == "archivo_invalido"
    assert cliente.llamadas == []  # validar es la validación barata: no gasta una llamada al LLM
    assert [t.a_estado for t in doc.transiciones] == [E.RECIBIDO, E.RECHAZADO]


def test_un_documento_ya_VALIDADO_entra_al_grafo_por_su_etapa_sin_volver_a_validar(repo, storage):
    doc = ingresar(repo, storage)
    ServicioIngesta(repo, storage).validar(doc)
    assert doc.estado == E.VALIDADO
    orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()])).procesar(doc)
    assert [t.a_estado for t in doc.transiciones] == [E.RECIBIDO, E.VALIDADO, E.CLASIFICADO, E.EXTRAIDO, E.EVALUADO, E.ENRUTADO]


def test_si_el_original_no_esta_en_memoria_validar_lo_relee_del_storage(repo, storage):
    """Reanudar el grafo en otro proceso (reintentos, trabajador) no depende de la memoria de la petición."""
    doc = ingresar(repo, storage)
    del doc.contenido_recibido
    r = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()])).procesar(doc)
    assert doc.estado == E.ENRUTADO
    assert r.extraccion.paciente.nombre == "Carlos Eduardo Mendes"


# --- Versiones y duplicados (RN-O2, RN-O3) ----------------------------------------------------


def test_version_nueva_no_vuelve_a_alertar_si_no_sube_de_prioridad_RN_O2(repo, storage):
    doc1 = ingresar(repo, storage)
    orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()])).procesar(doc1)
    doc2 = ingresar(repo, storage, request_caso_1(metadatos={"nota": "versión 2"}, contenido_texto=TEXTO_CASO_1 + "\nAddendum."))
    orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()])).procesar(doc2)
    assert doc2.version == 2
    assert repo.contar_alertas("DOC-CLIN-2026-8942") == 1


def test_mismo_contenido_con_otro_id_no_duplica_la_alerta_RN_O3(repo, storage):
    doc_a = ingresar(repo, storage)
    orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()])).procesar(doc_a)
    doc_b = ingresar(repo, storage, request_caso_1(documento_id="DOC-B"))
    r = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()])).procesar(doc_b)
    assert r.posible_duplicado_de == "DOC-CLIN-2026-8942"
    assert repo.alerta_activa(doc_b) is None
