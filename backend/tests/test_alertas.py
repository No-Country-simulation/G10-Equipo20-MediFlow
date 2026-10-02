"""Ciclo propio de las alertas críticas (RN-F2, RN-P7, RN-Q2, RN-Q4).

RN-Q2: el destinatario sale de la cadena de guardia que configura la clínica.
RN-F2: sin acuse en el plazo, la alerta escala al siguiente nivel y el escalamiento queda en el historial.
RN-P7: con el canal caído se usa el alternativo; si ninguno funciona, escala al siguiente rol y se registra.
Nada de esto corre dentro del grafo del documento: es un trabajo periódico sobre las alertas pendientes.
"""
from datetime import timedelta

import pytest

from app.packs.loader import cargar_umbrales
from app.repositories.documentos import RepositorioDocumentos
from app.services.alertas import CanalCaido, NotificadorFalso, ServicioAlertas
from app.services.llm import ClienteFalso, ServicioExtraccion
from app.services.orquestador import Orquestador
from tests.test_grafo import ingresar, request_caso_1
from tests.test_llm import propuesta_caso_1


@pytest.fixture
def repo(session):
    return RepositorioDocumentos(session)


def alerta_critica(repo, storage, notificador, documento_id="DOC-CLIN-2026-8942"):
    """Procesa el caso 1 (TEP agudo): genera una alerta crítica pendiente."""
    orq = Orquestador(repo, storage, ServicioExtraccion(ClienteFalso(respuestas=[propuesta_caso_1()]), max_intentos=1), notificador=notificador)
    doc = ingresar(repo, storage, request_caso_1(documento_id=documento_id))
    orq.procesar(doc)
    alerta = repo.alerta_activa(doc)
    assert alerta is not None and alerta.estado_acuse == "pendiente"
    return doc, alerta


def test_la_clinica_configura_la_cadena_de_guardia_y_los_canales_RN_Q2_RN_P7():
    notificaciones = cargar_umbrales().notificaciones
    assert notificaciones.cadena_guardia[0] == "Jefe de Urgencias"
    assert len(notificaciones.cadena_guardia) >= 3
    assert notificaciones.canales[:2] == ["Slack", "Correo"]


def test_la_alerta_sale_por_el_primer_canal_al_primer_nivel_de_la_cadena_RN_F1_RN_Q2(repo, storage):
    notificador = NotificadorFalso()
    doc, alerta = alerta_critica(repo, storage, notificador)
    assert (alerta.canal, alerta.destinatario) == ("Slack", "Jefe de Urgencias")
    assert notificador.enviados == [("Slack", "Jefe de Urgencias", doc.documento_id)]
    assert "Mendes" not in notificador.mensajes[0]  # RN-Q4


def test_con_el_canal_caido_se_usa_el_alternativo_y_queda_registrado_RN_P7(repo, storage):
    notificador = NotificadorFalso(caidos={"Slack"})
    doc, alerta = alerta_critica(repo, storage, notificador)
    assert alerta.canal == "Correo"
    assert alerta.destinatario == "Jefe de Urgencias"
    assert notificador.enviados == [("Correo", "Jefe de Urgencias", doc.documento_id)]
    assert [e["tipo"] for e in alerta.escalamientos] == ["canal_alternativo"]
    assert alerta.escalamientos[0]["de"] == "Slack" and alerta.escalamientos[0]["a"] == "Correo"


def test_si_ningun_canal_funciona_escala_al_siguiente_rol_y_se_registra_RN_P7(repo, storage):
    notificador = NotificadorFalso(caidos={"Slack", "Correo"}, caidos_para={"Jefe de Urgencias"})
    doc, alerta = alerta_critica(repo, storage, notificador)
    assert alerta.destinatario == "Coordinador Médico de Turno"
    assert alerta.estado_acuse == "pendiente"
    assert [e["tipo"] for e in alerta.escalamientos][-1] == "escalamiento"
    assert alerta.escalamientos[-1]["motivo"].startswith("RN-P7")
    assert notificador.enviados[-1][1] == "Coordinador Médico de Turno"


def test_sin_acuse_en_el_plazo_la_alerta_escala_y_queda_en_el_historial_RN_F2(repo, storage):
    notificador = NotificadorFalso()
    doc, alerta = alerta_critica(repo, storage, notificador)
    servicio = ServicioAlertas(repo, cargar_umbrales(), notificador)
    plazo = timedelta(minutes=cargar_umbrales().tiempos.escalamiento_sin_acuse_min)

    assert servicio.escalar_vencidas(ahora=alerta.emitida_en + plazo - timedelta(minutes=1)) == []
    assert alerta.destinatario == "Jefe de Urgencias"

    escaladas = servicio.escalar_vencidas(ahora=alerta.emitida_en + plazo)
    assert [a.documento_id for a in escaladas] == [doc.documento_id]
    assert alerta.destinatario == "Coordinador Médico de Turno"
    assert alerta.estado_acuse == "pendiente"  # sigue esperando acuse; el acuse lo da quien la atienda
    evento = alerta.escalamientos[-1]
    assert evento["tipo"] == "escalamiento" and evento["de"] == "Jefe de Urgencias" and evento["a"] == "Coordinador Médico de Turno"
    assert notificador.enviados[-1] == ("Slack", "Coordinador Médico de Turno", doc.documento_id)
    historial = doc.resultado_json["historial_decisiones"]
    assert historial[-1]["regla"] == "RN-F2" and "Coordinador Médico de Turno" in historial[-1]["decision"]


def test_cada_plazo_sin_acuse_sube_un_nivel_hasta_agotar_la_cadena_RN_F2(repo, storage):
    notificador = NotificadorFalso()
    doc, alerta = alerta_critica(repo, storage, notificador)
    umbrales = cargar_umbrales()
    servicio = ServicioAlertas(repo, umbrales, notificador)
    plazo = timedelta(minutes=umbrales.tiempos.escalamiento_sin_acuse_min)
    cadena = umbrales.notificaciones.cadena_guardia
    for n in range(1, len(cadena)):
        servicio.escalar_vencidas(ahora=alerta.emitida_en + plazo * n)
        assert alerta.destinatario == cadena[n]
    # cadena agotada: la alerta sigue pendiente en el último nivel, sin inventar un rol más
    assert servicio.escalar_vencidas(ahora=alerta.emitida_en + plazo * (len(cadena) + 2)) == []
    assert alerta.destinatario == cadena[-1]
    assert len([e for e in alerta.escalamientos if e["tipo"] == "escalamiento"]) == len(cadena) - 1


def test_una_alerta_acusada_no_escala_RN_F2_RN_Q5(repo, storage):
    notificador = NotificadorFalso()
    doc, alerta = alerta_critica(repo, storage, notificador)
    repo.acusar_alerta(alerta, "jefe.rojas")
    repo.guardar()
    servicio = ServicioAlertas(repo, cargar_umbrales(), notificador)
    assert servicio.escalar_vencidas(ahora=alerta.emitida_en + timedelta(hours=5)) == []
    assert alerta.destinatario == "Jefe de Urgencias"


def test_el_notificador_falso_modela_un_canal_caido():
    notificador = NotificadorFalso(caidos={"SMS"})
    with pytest.raises(CanalCaido):
        notificador.enviar("SMS", "alguien", "mensaje", None)


def test_la_api_expone_el_destinatario_vigente_y_los_escalamientos(client, llm_falso):
    llm_falso.respuestas.append(propuesta_caso_1())
    r = client.post("/documentos", json={"documento_id": "DOC-API", "canal_origen": "Guardia_Emergencias", "tipo_contenido": "texto",
                                         "contenido_texto": "Paciente: Carlos Mendes, 52 años. Fecha: 03/04/2026. TC: tromboembolismo pulmonar agudo. Dr. Rojas, RM 45678."})
    assert r.status_code == 200
    alerta = client.get("/alertas").json()[0]
    assert alerta["destinatario"] == "Jefe de Urgencias"
    assert alerta["escalamientos"] == []
