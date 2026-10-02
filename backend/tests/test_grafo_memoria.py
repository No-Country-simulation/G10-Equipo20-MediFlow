"""Memoria del grafo (checkpoints de LangGraph): el ciclo de vida se puede reanudar donde quedó.

RN-P2 habla de reintentos y de un documento "en espera de reintento"; RN-I4 de un documento bloqueado hasta que
una persona lo resuelva. Las dos cosas exigen que el grafo recuerde en qué etapa está cada documento fuera de la
memoria de una petición. Las tablas propias siguen siendo la verdad del negocio (RN-I3, RN-G2); el checkpoint solo
sirve para continuar. Por eso el estado que viaja por el grafo es JSON puro y vive en la misma base PostgreSQL.
"""
import json
import os

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.memoria import crear_memoria, hilo
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.resultado import EstadoDocumento as E
from app.services.llm import ClienteFalso, ServicioExtraccion
from app.services.orquestador import Orquestador
from tests.test_api_revision import propuesta_para_revision
from tests.test_grafo import ingresar, request_caso_1
from tests.test_llm import propuesta_caso_1


@pytest.fixture
def repo(session):
    return RepositorioDocumentos(session)


def orquestador(repo, storage, cliente, memoria) -> Orquestador:
    return Orquestador(repo, storage, ServicioExtraccion(cliente, max_intentos=2, espera_base_s=0, dormir=lambda s: None), memoria=memoria)


class ClienteQueSeCorta:
    """Simula un corte del proceso a mitad del nodo del LLM: no es un error transitorio, es la caída de todo."""

    def completar_estructurado(self, llamada):
        raise RuntimeError("corte de luz")


def test_cada_documento_y_version_tiene_su_propio_hilo(repo, storage):
    doc = ingresar(repo, storage)
    assert hilo(doc) == {"configurable": {"thread_id": "DOC-CLIN-2026-8942:v1"}}


def test_el_estado_que_viaja_por_el_grafo_es_json_puro(repo, storage):
    memoria = InMemorySaver()
    doc = ingresar(repo, storage)
    orq = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()]), memoria)
    orq.procesar(doc)
    historia = list(orq.grafo.get_state_history(hilo(doc)))
    assert len(historia) >= 5  # un checkpoint por etapa
    for punto in historia:
        json.dumps(punto.values)  # sin objetos de Python: se guarda y se lee desde cualquier proceso
    assert set(historia[0].values) <= {"documento_pk", "codigo_error", "error", "propuesta", "evaluacion", "resultado", "revision"}
    assert historia[0].next == ("entrega",)  # ENRUTADO: espera las confirmaciones de los destinos


def test_tras_un_corte_el_grafo_se_reanuda_en_la_etapa_donde_quedo_RN_P2(repo, storage):
    memoria = InMemorySaver()
    doc = ingresar(repo, storage)
    with pytest.raises(RuntimeError):
        orquestador(repo, storage, ClienteQueSeCorta(), memoria).procesar(doc)
    assert doc.estado == E.VALIDADO  # la validación quedó hecha y registrada

    # Otro proceso, con el motor de vuelta, retoma el mismo hilo: no vuelve a validar ni a recibir.
    r = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()]), memoria).reanudar(doc)
    assert doc.estado == E.ENRUTADO
    assert r.clasificacion.nivel_prioridad == "Crítico"
    assert [t.a_estado for t in doc.transiciones] == [E.RECIBIDO, E.VALIDADO, E.CLASIFICADO, E.EXTRAIDO, E.EVALUADO, E.ENRUTADO]


def test_sin_memoria_configurada_el_grafo_usa_memoria_en_ram(repo, storage):
    """Sin memoria el grafo no podría esperar a una persona (RN-I4): la suite unitaria usa la de RAM."""
    doc = ingresar(repo, storage)
    orq = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()]), None)
    assert isinstance(orq.memoria, InMemorySaver)
    assert orq.procesar(doc).estado is E.ENRUTADO


def test_la_memoria_se_elige_por_la_url_de_la_base():
    assert isinstance(crear_memoria("sqlite+pysqlite:///:memory:"), InMemorySaver)  # suite unitaria


URL_PG = os.environ.get("MEDIFLOW_TEST_DATABASE_URL", "")


@pytest.mark.skipif(not URL_PG.startswith("postgresql"), reason="la memoria del grafo vive en PostgreSQL; esta prueba corre contra una base real")
def test_la_memoria_del_grafo_vive_en_postgresql(repo, storage):
    from langgraph.checkpoint.postgres import PostgresSaver

    memoria = crear_memoria(URL_PG)
    assert isinstance(memoria, PostgresSaver)
    doc = ingresar(repo, storage, request_caso_1(documento_id=f"DOC-PG-{os.getpid()}"))
    orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()]), memoria).procesar(doc)
    assert memoria.get(hilo(doc)) is not None


@pytest.mark.skipif(not URL_PG.startswith("postgresql"), reason="la espera de la revisión humana se guarda en PostgreSQL; corre contra una base real")
def test_la_espera_de_la_revision_humana_sobrevive_en_postgresql_RN_I4(repo, storage):
    memoria = crear_memoria(URL_PG)
    doc = ingresar(repo, storage, request_caso_1(documento_id=f"DOC-PG-REV-{os.getpid()}"))
    orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_para_revision()]), memoria).procesar(doc)
    assert doc.estado == E.EN_REVISION_HUMANA
    # Otro proceso, con otra conexión a la misma base, encuentra el hilo esperando y lo resuelve.
    otro = orquestador(repo, storage, ClienteFalso(respuestas=[]), crear_memoria(URL_PG))
    assert otro.esperando_decision(doc)
    otro.resolver_revision(doc, accion="aprobar", usuario="ana", rol="auditor_clinico", motivo="confirmado")
    assert doc.estado == E.ENRUTADO
    assert not otro.esperando_decision(doc)
