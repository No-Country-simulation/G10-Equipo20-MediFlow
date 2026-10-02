"""La revisión humana como interrupción del grafo (RN-I4, RN-J3, RN-J4, RN-I6).

Cuando enrutar decide revisión humana, el grafo persiste, emite la alerta si corresponde y se detiene a esperar
a la persona. Aprobar, corregir, rechazar y transcribir reanudan el mismo hilo: corregir vuelve al nodo evaluar
(RN-J4) sin tocar el LLM; aprobar y rechazar cierran. El orquestador deja de re-ejecutar las reglas por su cuenta.
"""
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.memoria import hilo
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.resultado import EstadoDocumento as E, MotivoAuditoria as M
from app.services.errores import ErrorDeRevision
from app.services.llm import ClienteFalso, ErrorTransitorioLLM, ServicioExtraccion
from app.services.orquestador import Orquestador
from tests.test_aceptacion import TEXTO_RECETA
from tests.test_api_revision import TEXTO_RUTINA, propuesta_para_revision, propuesta_rutina_dudosa
from tests.test_api_transcripcion import transcripcion_receta
from tests.test_grafo import ingresar, request_caso_1
from tests.test_llm import propuesta_caso_1

ANA = {"usuario": "ana", "rol": "auditor_clinico"}


@pytest.fixture
def repo(session):
    return RepositorioDocumentos(session)


def orquestador(repo, storage, cliente, memoria) -> Orquestador:
    return Orquestador(repo, storage, ServicioExtraccion(cliente, max_intentos=2, espera_base_s=0, dormir=lambda s: None), memoria=memoria)


def esperando(orq, doc) -> bool:
    return orq.esperando_decision(doc)


def test_un_documento_en_revision_deja_el_grafo_esperando_la_decision_RN_I4(repo, storage):
    orq = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_para_revision()]), InMemorySaver())
    doc = ingresar(repo, storage)
    r = orq.procesar(doc)
    assert doc.estado == E.EN_REVISION_HUMANA
    assert r.evaluacion.requiere_auditoria_humana is True
    assert esperando(orq, doc)
    aviso = orq.grafo.get_state(hilo(doc)).tasks[0].interrupts[0].value
    assert aviso["documento_id"] == "DOC-CLIN-2026-8942"
    assert aviso["motivo_auditoria"] == M.CRITICO_BAJA_CONFIANZA.value
    assert "Mendes" not in str(aviso)  # RN-M4: la espera no lleva datos del paciente


def test_la_alerta_critica_sale_antes_de_esperar_a_la_persona_RN_I6_RN_D9(repo, storage):
    orq = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_para_revision()]), InMemorySaver())
    doc = ingresar(repo, storage)
    orq.procesar(doc)
    assert esperando(orq, doc)
    assert repo.alerta_activa(doc).estado_acuse == "pendiente"


def test_aprobar_reanuda_el_hilo_y_enruta_RN_J3(repo, storage):
    orq = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_para_revision()]), InMemorySaver())
    doc = ingresar(repo, storage)
    orq.procesar(doc)
    r = orq.resolver_revision(doc, accion="aprobar", motivo="hallazgo confirmado", **ANA)
    assert doc.estado == E.ENRUTADO
    assert r.enrutamiento.destino_principal == "Cola_Emergencia_Medica"
    assert r.evaluacion.requiere_auditoria_humana is False
    assert [t.a_estado for t in doc.transiciones][-3:] == [E.EN_REVISION_HUMANA, E.RESUELTO, E.ENRUTADO]
    assert doc.transiciones[-1].actor == "ana"  # RN-G4
    assert orq.grafo.get_state(hilo(doc)).next == ("entrega",)  # enrutado: ahora espera las confirmaciones


def test_corregir_vuelve_a_evaluar_por_el_grafo_sin_LLM_RN_J4_RN_J8(repo, storage):
    cliente = ClienteFalso(respuestas=[propuesta_rutina_dudosa()])
    orq = orquestador(repo, storage, cliente, InMemorySaver())
    doc = ingresar(repo, storage, request_caso_1(contenido_texto=TEXTO_RUTINA))
    orq.procesar(doc)
    assert esperando(orq, doc)
    r = orq.resolver_revision(doc, accion="corregir", motivo="clasificación confirmada", correcciones={"clasificacion.score_confianza": 0.99}, **ANA)
    assert doc.estado == E.ENRUTADO
    assert len(cliente.llamadas) == 1  # RN-J4: sin volver al LLM
    assert [t.a_estado for t in doc.transiciones][-4:] == [E.EN_REVISION_HUMANA, E.RESUELTO, E.EVALUADO, E.ENRUTADO]
    assert any(d.regla == "RN-J3" and d.decision == "corregido" for d in r.historial_decisiones)
    assert [(c.campo, c.extraido, c.corregido) for c in doc.correcciones] == [("clasificacion.score_confianza", 0.6, 0.99)]  # RN-J8
    assert orq.grafo.get_state(hilo(doc)).next == ("entrega",)


def test_corregir_puede_dejarlo_otra_vez_en_revision_y_el_grafo_vuelve_a_esperar(repo, storage):
    orq = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_rutina_dudosa()]), InMemorySaver())
    doc = ingresar(repo, storage, request_caso_1(contenido_texto=TEXTO_RUTINA))
    orq.procesar(doc)
    orq.resolver_revision(doc, accion="corregir", motivo="sigo dudando", correcciones={"clasificacion.score_confianza": 0.7}, **ANA)
    assert doc.estado == E.EN_REVISION_HUMANA
    assert esperando(orq, doc)
    orq.resolver_revision(doc, accion="aprobar", motivo="ahora sí", **ANA)
    assert doc.estado == E.ENRUTADO


def test_rechazar_cierra_el_hilo_RN_I5_RN_J3(repo, storage):
    orq = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_para_revision()]), InMemorySaver())
    doc = ingresar(repo, storage)
    orq.procesar(doc)
    r = orq.resolver_revision(doc, accion="rechazar", motivo="documento de otra institución", **ANA)
    assert doc.estado == E.RECHAZADO
    assert r.estado is E.RECHAZADO
    assert orq.grafo.get_state(hilo(doc)).next == ()


def test_una_decision_invalida_no_mueve_el_documento_y_el_hilo_sigue_esperando(repo, storage):
    orq = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_para_revision()]), InMemorySaver())
    doc = ingresar(repo, storage)
    orq.procesar(doc)
    with pytest.raises(ErrorDeRevision) as error:
        orq.resolver_revision(doc, accion="rechazar", motivo="", **ANA)
    assert error.value.codigo == 422
    assert doc.estado == E.EN_REVISION_HUMANA
    assert esperando(orq, doc)
    orq.resolver_revision(doc, accion="rechazar", motivo="ahora con motivo", **ANA)
    assert doc.estado == E.RECHAZADO


def test_transcribir_reanuda_el_hilo_tras_un_fallo_tecnico_RN_P2_RN_J4(repo, storage):
    orq = orquestador(repo, storage, ClienteFalso(respuestas=[ErrorTransitorioLLM("caído")] * 2), InMemorySaver())
    doc = ingresar(repo, storage, request_caso_1(documento_id="FT-REC", canal_origen="Consulta_Ambulatoria", contenido_texto=TEXTO_RECETA))
    r = orq.procesar(doc)
    assert r.evaluacion.motivo_auditoria is M.FALLO_TECNICO
    assert esperando(orq, doc)
    r = orq.resolver_revision(doc, accion="transcribir", motivo="transcrito desde el original", transcripcion=transcripcion_receta(), **ANA)
    assert doc.estado == E.ENRUTADO
    assert r.enrutamiento.destino_principal == "Farmacia_Hospitalaria"
    assert [t.a_estado for t in doc.transiciones][-3:] == [E.RESUELTO, E.EVALUADO, E.ENRUTADO]


def test_un_documento_en_revision_anterior_a_la_memoria_se_resuelve_igual(repo, storage):
    """Los documentos que entraron a revisión antes de que el grafo tuviera memoria no tienen hilo: se les abre uno."""
    orq = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_para_revision()]), InMemorySaver())
    doc = ingresar(repo, storage)
    orq.procesar(doc)
    otro = orquestador(repo, storage, ClienteFalso(respuestas=[]), InMemorySaver())  # memoria nueva: no sabe nada del hilo
    r = otro.resolver_revision(doc, accion="aprobar", motivo="hallazgo confirmado", **ANA)
    assert doc.estado == E.ENRUTADO
    assert r.estado is E.ENRUTADO
    assert [t.a_estado for t in doc.transiciones][-3:] == [E.EN_REVISION_HUMANA, E.RESUELTO, E.ENRUTADO]


def test_sin_memoria_configurada_el_grafo_usa_memoria_en_ram_para_poder_esperar(repo, storage):
    orq = Orquestador(repo, storage, ServicioExtraccion(ClienteFalso(respuestas=[propuesta_para_revision()]), max_intentos=1))
    doc = ingresar(repo, storage)
    orq.procesar(doc)
    assert esperando(orq, doc)
    orq.resolver_revision(doc, accion="aprobar", motivo="ok", **ANA)
    assert doc.estado == E.ENRUTADO
