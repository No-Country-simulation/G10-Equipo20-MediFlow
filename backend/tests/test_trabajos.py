"""Cola persistente de procesamiento (RN-P2, RN-P5): la petición guarda el original y deja un trabajo; un worker
aparte corre el grafo, renueva su arriendo y, si cae, otro lo retoma. Agotados los intentos, el documento va a
revisión humana por fallo técnico (RN-P4) y la persona puede pedir que el motor vuelva a leer."""
from datetime import datetime, timedelta, timezone

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.api.deps import get_memoria
from app.core.config import get_settings
from app.main import app
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.resultado import EstadoDocumento as E
from app.services.llm import ClienteFalso, ServicioExtraccion
from app.services.orquestador import Orquestador
from app.services.trabajos import ServicioTrabajos, atender
from tests.test_api_documentos import CUERPO, MUESTRAS
from tests.test_grafo import ingresar, request_caso_1
from tests.test_grafo_memoria import ClienteQueSeCorta
from tests.test_llm import propuesta_caso_1

T0 = datetime.now(timezone.utc) + timedelta(days=1)  # un instante posterior a la creación de los trabajos


def orquestador(repo, storage, cliente, memoria) -> Orquestador:
    return Orquestador(repo, storage, ServicioExtraccion(cliente, max_intentos=2, espera_base_s=0, dormir=lambda s: None), memoria=memoria)


@pytest.fixture
def repo(session):
    return RepositorioDocumentos(session)


def test_encolar_es_idempotente_y_solo_acepta_lo_que_el_grafo_puede_empezar(repo, storage, session):
    doc = ingresar(repo, storage)
    cola = ServicioTrabajos(session)
    primero = cola.encolar(doc, solicitado_por="ana")
    assert primero.estado == "EN_COLA" and primero.intento == 0 and primero.solicitado_por == "ana"
    assert cola.encolar(doc).id == primero.id  # un documento tiene a lo sumo un trabajo vivo
    assert cola.pendientes() == 1
    orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()]), InMemorySaver()).procesar(doc)
    with pytest.raises(ValueError):
        cola.encolar(doc)  # ya ENRUTADO: no hay nada que procesar


def test_el_worker_toma_el_trabajo_mas_antiguo_y_corre_el_grafo_hasta_enrutar(repo, storage, session):
    doc = ingresar(repo, storage)
    otro = ingresar(repo, storage, request_caso_1(documento_id="DOC-SEGUNDO"))
    cola = ServicioTrabajos(session)
    cola.encolar(doc)
    cola.encolar(otro)
    session.commit()
    trabajo = cola.reclamar(ahora=T0)
    assert trabajo.documento_id == doc.documento_id and trabajo.estado == "EN_CURSO" and trabajo.intento == 1 and trabajo.token
    assert trabajo.arrendado_hasta.replace(tzinfo=timezone.utc) == T0 + timedelta(seconds=cola.arriendo_s)
    atender(session, trabajo, orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()]), InMemorySaver()), cola)
    assert doc.estado == E.ENRUTADO and doc.nivel_prioridad == "Crítico"
    assert trabajo.estado == "TERMINADO" and trabajo.token is None and trabajo.codigo_error is None
    assert cola.reclamar(ahora=T0).documento_id == "DOC-SEGUNDO"  # el siguiente de la cola


def test_un_arriendo_vencido_lo_retoma_otro_worker_RN_P2(repo, storage, session):
    doc = ingresar(repo, storage)
    cola = ServicioTrabajos(session, arriendo_s=300)
    cola.encolar(doc)
    session.commit()
    caido = cola.reclamar(ahora=T0)  # este worker muere sin decir nada
    token_caido = caido.token
    assert cola.reclamar(ahora=T0 + timedelta(seconds=299)) is None  # el arriendo sigue vigente: nadie se lo quita
    retomado = cola.reclamar(ahora=T0 + timedelta(seconds=301))
    assert retomado.id == caido.id and retomado.intento == 2 and retomado.token != token_caido
    assert not cola.renovar(retomado.id, token_caido)  # el latido del worker caído ya no cuenta
    assert cola.renovar(retomado.id, retomado.token)
    atender(session, retomado, orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()]), InMemorySaver()), cola)
    assert doc.estado == E.ENRUTADO and retomado.estado == "TERMINADO"


def test_un_fallo_reencola_con_espera_y_agotados_los_intentos_va_a_revision_humana_RN_P4(repo, storage, session):
    doc = ingresar(repo, storage)
    memoria = InMemorySaver()
    cola = ServicioTrabajos(session, intentos_maximos=2)
    cola.encolar(doc)
    session.commit()
    trabajo = cola.reclamar(ahora=T0)
    atender(session, trabajo, orquestador(repo, storage, ClienteQueSeCorta(), memoria), cola, ahora=T0)
    assert trabajo.estado == "EN_COLA" and trabajo.intento == 1 and trabajo.codigo_error.startswith("RuntimeError")
    assert doc.estado == E.VALIDADO  # la validación sin LLM quedó confirmada; lo del motor, no
    assert cola.reclamar(ahora=T0 + timedelta(seconds=5)) is None  # espera antes del siguiente intento
    trabajo = cola.reclamar(ahora=T0 + timedelta(seconds=20))
    assert trabajo.intento == 2
    atender(session, trabajo, orquestador(repo, storage, ClienteQueSeCorta(), memoria), cola, ahora=T0 + timedelta(seconds=20))
    assert trabajo.estado == "FALLIDO"
    assert doc.estado == E.EN_REVISION_HUMANA
    assert [t.a_estado for t in doc.transiciones][-2:] == [E.FALLO_TECNICO, E.EN_REVISION_HUMANA]
    assert doc.resultado_json["evaluacion"]["motivo_auditoria"] == "fallo_tecnico"
    assert doc.nivel_prioridad == "Crítico"  # RN-P4: el texto del caso 1 nombra un TEP; la detección determinística alertó igual
    assert doc.resultado_json["notificacion_generada"] is not None
    # El motor vuelve y la persona pide que lea de nuevo: el hilo esperaba la decisión.
    de_vuelta = orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()]), memoria)
    assert de_vuelta.esperando_decision(doc)
    de_vuelta.resolver_revision(doc, accion="reintentar", usuario="ana", rol="auditor_clinico", motivo="motor de vuelta")
    assert doc.estado == E.ENRUTADO


def test_un_trabajo_de_un_documento_que_otro_proceso_ya_termino_no_hace_nada(repo, storage, session):
    doc = ingresar(repo, storage)
    cola = ServicioTrabajos(session)
    cola.encolar(doc)
    session.commit()
    trabajo = cola.reclamar(ahora=T0)
    orquestador(repo, storage, ClienteFalso(respuestas=[propuesta_caso_1()]), InMemorySaver()).procesar(doc)  # en línea, mientras tanto
    cliente = ClienteFalso(respuestas=[])
    atender(session, trabajo, orquestador(repo, storage, cliente, InMemorySaver()), cola)
    assert trabajo.estado == "TERMINADO" and cliente.llamadas == [] and doc.estado == E.ENRUTADO


# --- API -----------------------------------------------------------------------------------------


@pytest.fixture
def modo_worker(monkeypatch):
    monkeypatch.setattr(get_settings(), "procesamiento_en_worker", True)


def test_en_modo_worker_la_api_acepta_con_202_y_el_worker_termina_el_triaje(client, session, storage, llm_falso, modo_worker):
    r = client.post("/documentos", json=CUERPO)
    assert r.status_code == 202
    cuerpo = r.json()
    assert cuerpo["estado"] == "RECIBIDO" and cuerpo["trabajo"]["estado"] == "EN_COLA" and cuerpo["trabajo"]["intento"] == 0
    assert llm_falso.llamadas == []  # la petición no esperó al motor
    assert client.get("/documentos/DOC-CLIN-2026-8942").json()["trabajo"]["estado"] == "EN_COLA"
    assert client.get("/documentos/DOC-CLIN-2026-8942/trabajo").json()["estado"] == "EN_COLA"
    assert client.get("/health").json()["procesamiento"] == "worker"
    assert client.post("/documentos", json=CUERPO).json()["duplicado"] is True  # RN-O1 sigue antes de la cola

    llm_falso.respuestas.append(propuesta_caso_1())
    cola = ServicioTrabajos(session)
    repo = RepositorioDocumentos(session)
    trabajo = cola.reclamar()
    atender(session, trabajo, Orquestador(repo, storage, ServicioExtraccion(llm_falso, max_intentos=1), memoria=app.dependency_overrides[get_memoria]()), cola)
    detalle = client.get("/documentos/DOC-CLIN-2026-8942").json()
    assert detalle["estado"] == "ENRUTADO" and detalle["nivel_prioridad"] == "Crítico" and detalle["trabajo"]["estado"] == "TERMINADO"
    assert client.post("/documentos/DOC-CLIN-2026-8942/procesar").status_code == 409  # ya no hay nada que procesar


def test_en_modo_worker_cada_parte_de_un_pdf_compuesto_tiene_su_trabajo_RN_O4(client, session, modo_worker):
    r = client.post("/documentos/archivo", data={"documento_id": "DOC-COMP", "canal_origen": "Externo", "paginas_por_documento": "1,2"},
                    files={"archivo": ("cardio_mixed.pdf", (MUESTRAS / "cardio_mixed.pdf").read_bytes(), "application/pdf")})
    assert r.status_code == 202
    partes = r.json()["sub_documentos"]
    assert len(partes) == 2 and all(p["trabajo"]["estado"] == "EN_COLA" for p in partes)
    assert ServicioTrabajos(session).pendientes() == 2


def test_sin_trabajo_el_endpoint_del_trabajo_responde_404(client, llm_falso):
    llm_falso.respuestas.append(propuesta_caso_1())
    client.post("/documentos", json=CUERPO)
    assert client.get("/documentos/DOC-CLIN-2026-8942/trabajo").status_code == 404
    assert client.get("/documentos/DOC-CLIN-2026-8942").json()["trabajo"] is None


def test_un_documento_que_quedo_sin_procesar_se_procesa_a_pedido(client, session, storage, llm_falso):
    doc = ingresar(RepositorioDocumentos(session), storage)  # recibido, pero nadie corrió el grafo (worker apagado)
    assert doc.estado == E.RECIBIDO
    llm_falso.respuestas.append(propuesta_caso_1())
    r = client.post("/documentos/DOC-CLIN-2026-8942/procesar")
    assert r.status_code == 200 and r.json()["estado"] == "ENRUTADO"
    assert client.post("/documentos/DOC-CLIN-2026-8942/procesar").status_code == 409
