"""Fallas del flujo de revisión humana que no deben dejar un caso sin salida (RN-I4, RN-O2, RN-F1, RN-J5, RN-L1, RN-P6).

Cada prueba describe una situación real: llega otra versión mientras el caso espera, se rechaza o se baja un
Crítico con alerta pendiente, el plan tras revisión apunta a un destino que la clínica desactivó, o falla la base
a mitad de una decisión. El sistema debe dejar siempre un camino para resolverlo.
"""
import pytest

from app.repositories.documentos import RepositorioDocumentos
from tests.test_aceptacion import med, receta, TEXTO_RECETA
from tests.test_api_configuracion import proponer
from tests.test_api_revision import enviar, propuesta_para_revision, TEXTO


def resolver(client, documento_id, **cuerpo):
    return client.post(f"/revision/{documento_id}/resolver", json=cuerpo)


# --- otra versión mientras el caso espera (RN-O2) ------------------------------------------------------


def test_RN_O2_una_version_nueva_cierra_la_anterior_que_esperaba_revision(client, llm_falso, jefe):
    enviar(client, llm_falso, "DOC-V", propuesta_para_revision())
    assert client.get("/documentos/DOC-V").json()["estado"] == "EN_REVISION_HUMANA"
    resolver(client, "DOC-V", accion="reasignar", asignar_a="jefe.rojas")
    enviar(client, llm_falso, "DOC-V", propuesta_para_revision(), texto=TEXTO + " Informe ampliado.")  # versión 2

    cola = client.get("/revision").json()
    assert [(c["documento_id"], c["version"]) for c in cola] == [("DOC-V", 2)]  # la versión 1 ya no espera a nadie
    assert cola[0]["asignado_a"] is None  # la versión nueva empieza sin dueño
    detalle = client.get("/documentos/DOC-V").json()
    assert detalle["version"] == 2 and detalle["estado"] == "EN_REVISION_HUMANA"
    r = resolver(client, "DOC-V", accion="aprobar", motivo="confirmado")  # actúa sobre la versión 2
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["estado"] == "ENRUTADO"
    assert client.get("/revision").json() == []


def test_RN_O2_la_version_reemplazada_queda_rechazada_con_motivo(client, llm_falso, session):
    enviar(client, llm_falso, "DOC-V", propuesta_para_revision())
    enviar(client, llm_falso, "DOC-V", propuesta_para_revision(), texto=TEXTO + " Informe ampliado.")
    from sqlalchemy import select
    from app.models.documento import Documento
    v1 = session.scalars(select(Documento).where(Documento.documento_id == "DOC-V", Documento.version == 1)).one()
    assert v1.estado == "RECHAZADO"
    assert v1.transiciones[-1].actor == "sistema" and "RN-O2" in v1.transiciones[-1].motivo and "versión 2" in v1.transiciones[-1].motivo
    # la alerta crítica de la versión 1 sigue viva: la versión 2 no sube de nivel y no vuelve a alertar (RN-O2)
    alertas = client.get("/alertas").json()
    assert [(a["documento_id"], a["version"], a["estado_acuse"]) for a in alertas] == [("DOC-V", 1, "pendiente")]


# --- rechazar o bajar un Crítico con alerta pendiente (RN-F1, RN-J5) -------------------------------------


def test_rechazar_un_critico_cierra_su_alerta_pendiente_a_nombre_de_quien_rechaza(client, llm_falso, notificador_falso):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    assert client.get("/alertas", params={"estado_acuse": "pendiente"}).json()[0]["documento_id"] == "DOC-CRIT"
    r = resolver(client, "DOC-CRIT", accion="rechazar", motivo="documento de otra institución")
    assert r.status_code == 200 and r.json()["estado"] == "RECHAZADO"
    assert client.get("/alertas", params={"estado_acuse": "pendiente"}).json() == []
    alerta = client.get("/documentos/DOC-CRIT").json()["alerta"]
    assert alerta["estado_acuse"] == "acusado" and alerta["acusado_por"] == "aud.ana"
    cierre = client.get("/alertas").json()[0]["escalamientos"][-1]
    assert cierre["tipo"] == "cierre" and "rechazado" in cierre["motivo"] and cierre["por"] == "aud.ana"
    historial = r.json()["resultado"]["historial_decisiones"]
    assert any(d["regla"] == "RN-F1" and d["decision"] == "alerta cerrada" for d in historial)


def test_bajar_un_critico_cierra_su_alerta_y_queda_en_el_historial(client, llm_falso):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    r = resolver(client, "DOC-CRIT", accion="corregir", motivo="hallazgo descartado en el informe original",
                 correcciones={"nivel_prioridad": "Urgente", "extraccion.hallazgos_criticos_detectados": [], "extraccion.diagnosticos[0].cie10_sugerido": "J18.9"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ENRUTADO" and r.json()["resultado"]["clasificacion"]["nivel_prioridad"] == "Urgente"
    assert client.get("/alertas", params={"estado_acuse": "pendiente"}).json() == []
    cierre = client.get("/alertas").json()[0]["escalamientos"][-1]
    assert cierre["tipo"] == "cierre" and "Urgente" in cierre["motivo"]


# --- aprobar hacia un destino que la clínica desactivó (RN-L1) -----------------------------------------


def test_aprobar_no_entrega_a_un_destino_desactivado(client, llm_falso, gestor, gestor2):
    """El plan del TEP es Emergencia médica + Historia clínica. Con Historia clínica desactivada después de evaluar,
    aprobar entrega solo a Emergencia y deja constancia del destino omitido."""
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    assert client.get("/documentos/DOC-CRIT").json()["resultado"]["enrutamiento"]["destinos_tras_revision"] == ["Cola_Emergencia_Medica", "Historia_Clinica_Electronica"]
    p = proponer(gestor, {"destinos_inactivos": ["Historia_Clinica_Electronica"]}, motivo="la historia clínica se integra después").json()
    gestor.post(f"/configuracion/propuestas/{p['id']}/aprobar")
    assert gestor2.post(f"/configuracion/propuestas/{p['id']}/aprobar").json()["estado"] == "vigente"

    r = resolver(client, "DOC-CRIT", accion="aprobar", motivo="hallazgo confirmado")
    assert r.status_code == 200, r.text
    enrutamiento = r.json()["resultado"]["enrutamiento"]
    assert enrutamiento["destino_principal"] == "Cola_Emergencia_Medica" and enrutamiento["destinos_secundarios"] == []
    assert any(d["regla"] == "RN-L1" and "Historia_Clinica_Electronica" in d["evidencia"] for d in r.json()["resultado"]["historial_decisiones"])


def test_aprobar_sin_ningun_destino_activo_en_el_plan_es_409_y_explica_que_hacer(client, llm_falso, gestor, gestor2, monkeypatch):
    from app.services.orquestador import Orquestador

    enviar(client, llm_falso, "REC-1", receta([med("losartan", "50 mg")], **{"confianzas.medicamento_dosis": 0.90}), texto=TEXTO_RECETA, canal="Consulta_Ambulatoria")
    assert client.get("/documentos/REC-1").json()["estado"] == "EN_REVISION_HUMANA"
    # la configuración vigente desactiva todo lo que había en el plan (Farmacia e Historia clínica)
    monkeypatch.setattr(Orquestador, "_destinos_activos", lambda self, plan: [])
    r = resolver(client, "REC-1", accion="aprobar", motivo="x")
    assert r.status_code == 409 and "destino" in r.json()["detail"].lower()
    assert client.get("/documentos/REC-1").json()["estado"] == "EN_REVISION_HUMANA"  # sigue esperando una decisión válida


# --- una falla a mitad de la decisión no deja el caso atascado (RN-P6) ------------------------------------


def test_si_la_base_falla_al_aplicar_la_decision_el_caso_sigue_en_revision_y_se_puede_reintentar(client, llm_falso, session, monkeypatch):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    original = RepositorioDocumentos.guardar
    intentos = {"n": 0}

    def guardar_fallando(self):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise RuntimeError("conexión perdida con la base")
        return original(self)

    monkeypatch.setattr(RepositorioDocumentos, "guardar", guardar_fallando)
    with pytest.raises(RuntimeError):
        resolver(client, "DOC-CRIT", accion="aprobar", motivo="confirmado")
    session.rollback()  # lo que hace get_session al cerrar una petición que falló: nada queda a medias
    monkeypatch.setattr(RepositorioDocumentos, "guardar", original)
    detalle = client.get("/documentos/DOC-CRIT").json()
    assert detalle["estado"] == "EN_REVISION_HUMANA"  # nada a medias: la decisión no se aplicó
    assert resolver(client, "DOC-CRIT", accion="aprobar", motivo="confirmado").json()["estado"] == "ENRUTADO"  # el reintento funciona


# --- corregir el nombre del paciente (RN-A4, RN-G7) ---------------------------------------------------------


def test_corregir_el_nombre_del_paciente_actualiza_nombre_y_nome(client, llm_falso):
    enviar(client, llm_falso, "DOC-CRIT", propuesta_para_revision())
    r = resolver(client, "DOC-CRIT", accion="corregir", motivo="apellido según el documento", correcciones={"extraccion.paciente.nombre": "Carlos Eduardo Méndez"})
    assert r.status_code == 200, r.text
    paciente = r.json()["resultado"]["extraccion"]["paciente"]
    assert paciente["nombre"] == "Carlos Eduardo Méndez" and paciente["nome"] == "Carlos Eduardo Méndez"


def test_una_decision_tomada_sobre_una_version_vieja_se_rechaza_con_409(client, llm_falso):
    enviar(client, llm_falso, "DOC-V", propuesta_para_revision())
    enviar(client, llm_falso, "DOC-V", propuesta_para_revision(), texto=TEXTO + " Informe ampliado.")  # llega la versión 2
    r = resolver(client, "DOC-V", accion="aprobar", motivo="confirmado", version=1)  # la pantalla todavía mostraba la 1
    assert r.status_code == 409 and "versión 2" in r.json()["detail"]
    assert client.get("/documentos/DOC-V").json()["estado"] == "EN_REVISION_HUMANA"
    assert resolver(client, "DOC-V", accion="aprobar", motivo="confirmado", version=2).status_code == 200
