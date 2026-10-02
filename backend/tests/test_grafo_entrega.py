"""La entrega como segunda interrupción del grafo (sección 3.3, RN-I, RN-J7, RN-A4).

Enrutado es una decisión; Entregado es un hecho que confirman los destinos. Entre las dos el grafo espera: cada
confirmación, el acuse de la alerta y las verificaciones de Farmacia o Autorizaciones reanudan el mismo hilo, y el
documento cierra solo cuando no queda nada pendiente. Un crítico no cierra sin acuse (RN-J7).
"""
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.memoria import hilo
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.resultado import EstadoDocumento as E
from app.services.errores import ErrorDeRevision
from app.services.llm import ClienteFalso, ServicioExtraccion
from app.services.orquestador import Orquestador
from tests.test_api_revision import propuesta_para_revision
from tests.test_grafo import ingresar
from tests.test_llm import propuesta_caso_1


@pytest.fixture
def repo(session):
    return RepositorioDocumentos(session)


def orquestador(repo, storage, respuestas, memoria=None) -> Orquestador:
    return Orquestador(repo, storage, ServicioExtraccion(ClienteFalso(respuestas=respuestas), max_intentos=1), memoria=memoria or InMemorySaver())


def test_tras_enrutar_el_grafo_espera_las_confirmaciones(repo, storage):
    orq = orquestador(repo, storage, [propuesta_caso_1()])
    doc = ingresar(repo, storage)
    orq.procesar(doc)
    assert doc.estado == E.ENRUTADO
    assert orq.esperando_entrega(doc)
    aviso = orq.grafo.get_state(hilo(doc)).tasks[0].interrupts[0].value
    assert "Cola_Emergencia_Medica" in aviso["pendientes"]
    assert "acuse_alerta" in aviso["pendientes"]  # RN-J7
    assert "Mendes" not in str(aviso)  # RN-M4


def test_cada_confirmacion_reanuda_el_hilo_y_el_critico_cierra_solo_con_acuse_RN_J7(repo, storage):
    orq = orquestador(repo, storage, [propuesta_caso_1()])
    doc = ingresar(repo, storage)
    orq.procesar(doc)
    r = orq.entregar(doc, "Cola_Emergencia_Medica")
    assert doc.estado == E.ENRUTADO
    assert r["pendientes"] == ["acuse_alerta"]  # la HCE queda retenida sin identificador (RN-A4): no bloquea
    assert orq.esperando_entrega(doc)
    orq.acusar(doc, "jefe.rojas")
    assert doc.estado == E.ENTREGADO
    assert not orq.esperando_entrega(doc)
    assert orq.grafo.get_state(hilo(doc)).next == ()  # el hilo terminó: ENTREGADO es final (RN-I1)
    assert doc.transiciones[-1].a_estado == E.ENTREGADO


def test_un_destino_fuera_del_plan_no_toca_el_hilo(repo, storage):
    orq = orquestador(repo, storage, [propuesta_caso_1()])
    doc = ingresar(repo, storage)
    orq.procesar(doc)
    with pytest.raises(ErrorDeRevision) as error:
        orq.entregar(doc, "Farmacia_Hospitalaria")
    assert error.value.codigo == 400
    assert orq.esperando_entrega(doc)
    assert doc.estado == E.ENRUTADO


def test_aprobar_en_revision_lleva_el_hilo_a_esperar_la_entrega(repo, storage):
    orq = orquestador(repo, storage, [propuesta_para_revision()])
    doc = ingresar(repo, storage)
    orq.procesar(doc)
    assert orq.esperando_decision(doc)
    orq.resolver_revision(doc, accion="aprobar", usuario="ana", rol="auditor_clinico", motivo="confirmado")
    assert doc.estado == E.ENRUTADO
    assert orq.esperando_entrega(doc)


def test_un_documento_enrutado_anterior_a_la_memoria_se_entrega_igual(repo, storage):
    orq = orquestador(repo, storage, [propuesta_caso_1()])
    doc = ingresar(repo, storage)
    orq.procesar(doc)
    otro = orquestador(repo, storage, [], memoria=InMemorySaver())  # no sabe nada del hilo
    otro.entregar(doc, "Cola_Emergencia_Medica")
    otro.acusar(doc, "jefe.rojas")
    assert doc.estado == E.ENTREGADO


def test_el_acuse_de_un_documento_en_revision_no_abre_la_entrega_RN_D9(repo, storage):
    orq = orquestador(repo, storage, [propuesta_para_revision()])
    doc = ingresar(repo, storage)
    orq.procesar(doc)
    r = orq.acusar(doc, "jefe.rojas")  # RN-D9: la alerta se acusa aunque el documento siga en revisión
    assert r["estado_acuse"] == "acusado"
    assert doc.estado == E.EN_REVISION_HUMANA
    assert orq.esperando_decision(doc)
    assert not orq.esperando_entrega(doc)
