"""RN-M6, segunda parte: el titular pide que una persona revise una decisión automatizada.

El paciente no entra al sistema: el auditor registra la solicitud en su ficha y otra revisión humana la responde,
dentro del plazo legal del pack (Colombia: Ley 1581 de 2012, art. 15, quince días hábiles).
"""
from datetime import datetime, timezone

import pytest

from app.packs.loader import cargar_pack
from app.services.solicitudes_titular import vencimiento
from tests.test_aceptacion import med, receta, TEXTO_RECETA
from tests.test_api_farmacia_autorizaciones import enviar


def ficha_de_ana(client, llm_falso) -> dict:
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    enviar(client, llm_falso, "REC-2", TEXTO_RECETA.replace("30 (treinta)", "60 (sesenta)"),
           receta([med("losartan", "50 mg", cantidad_numeros="60", cantidad_letras="sesenta")]))
    ana = next(p for p in client.get("/pacientes").json()["items"] if p["nombre"] == "Ana María Pérez")
    return client.get(f"/pacientes/{ana['id']}").json()


def registrar(client, paciente_id, **cuerpo):
    datos = {"documento_id": "REC-1", "motivo": "no estoy de acuerdo con la prioridad asignada", **cuerpo}
    return client.post(f"/pacientes/{paciente_id}/solicitudes", json=datos)


# --- regla pura: el plazo cuenta días hábiles ---------------------------------------------------


@pytest.mark.parametrize("desde, dias, hasta", [
    (datetime(2026, 10, 5, 10, tzinfo=timezone.utc), 1, datetime(2026, 10, 6, 10, tzinfo=timezone.utc)),   # lunes -> martes
    (datetime(2026, 10, 9, 10, tzinfo=timezone.utc), 1, datetime(2026, 10, 12, 10, tzinfo=timezone.utc)),  # viernes -> lunes
    (datetime(2026, 10, 10, 10, tzinfo=timezone.utc), 1, datetime(2026, 10, 12, 10, tzinfo=timezone.utc)), # sábado -> lunes
    (datetime(2026, 10, 5, 10, tzinfo=timezone.utc), 15, datetime(2026, 10, 26, 10, tzinfo=timezone.utc)), # tres semanas
])
def test_el_plazo_salta_los_fines_de_semana(desde, dias, hasta):
    assert vencimiento(desde, dias) == hasta


def test_el_pack_colombia_declara_el_plazo_de_la_ley_1581():
    assert cargar_pack("CO").datos_personales.plazo_reclamo_dias_habiles == 15


# --- registrar ---------------------------------------------------------------------------------


def test_RN_M6_el_auditor_registra_la_solicitud_del_titular_en_la_ficha_con_plazo(client, llm_falso):
    ficha = ficha_de_ana(client, llm_falso)
    assert ficha["solicitudes"] == []
    r = registrar(client, ficha["id"], presentada_por="representante", canal="escrito")
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["estado"] == "pendiente" and s["documento_id"] == "REC-1" and s["version"] == 1
    assert s["presentada_por"] == "representante" and s["canal"] == "escrito"
    assert s["registrada_por"] == "aud.ana" and s["resultado"] is None and s["respuesta"] is None
    assert datetime.fromisoformat(s["vence_en"]) == vencimiento(datetime.fromisoformat(s["registrada_en"]), 15)

    ficha = client.get(f"/pacientes/{ficha['id']}").json()
    assert [x["id"] for x in ficha["solicitudes"]] == [s["id"]]
    # el revisor la ve al abrir el documento, con la ficha a un clic
    detalle = client.get("/documentos/REC-1").json()
    assert detalle["solicitud_titular"]["id"] == s["id"] and detalle["solicitud_titular"]["paciente_id"] == ficha["id"]
    assert client.get("/documentos/REC-2").json()["solicitud_titular"] is None


def test_la_solicitud_exige_motivo_y_un_documento_de_la_ficha_y_no_se_duplica(client, llm_falso):
    ficha = ficha_de_ana(client, llm_falso)
    assert registrar(client, ficha["id"], motivo="  ").status_code == 422
    assert registrar(client, ficha["id"], documento_id="DOC-AJENO").status_code == 422
    assert registrar(client, ficha["id"], canal="paloma").status_code == 422
    assert registrar(client, 9999).status_code == 404
    assert registrar(client, ficha["id"]).status_code == 201
    assert registrar(client, ficha["id"]).status_code == 409  # ya hay una pendiente sobre REC-1
    assert registrar(client, ficha["id"], documento_id="REC-2").status_code == 201


def test_RN_K2_solo_el_auditor_clinico_registra_y_responde(client, llm_falso, quimico, gestor):
    ficha = ficha_de_ana(client, llm_falso)
    assert registrar(gestor, ficha["id"]).status_code == 403
    assert registrar(quimico, ficha["id"]).status_code == 403  # el directorio es del auditor clínico
    s = registrar(client, ficha["id"]).json()
    r = quimico.post(f"/pacientes/solicitudes/{s['id']}/responder", json={"resultado": "mantenida", "respuesta": "x"})
    assert r.status_code == 403


# --- responder ---------------------------------------------------------------------------------


def test_RN_M6_la_respuesta_la_firma_quien_revisa_y_cierra_la_solicitud(client, llm_falso):
    ficha = ficha_de_ana(client, llm_falso)
    s = registrar(client, ficha["id"]).json()
    responder = f"/pacientes/solicitudes/{s['id']}/responder"
    assert client.post(responder, json={"resultado": "mantenida", "respuesta": " "}).status_code == 422
    assert client.post(responder, json={"resultado": "anulada", "respuesta": "x"}).status_code == 422
    r = client.post(responder, json={"resultado": "corregida", "respuesta": "se bajó la prioridad tras revisar el informe original"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["estado"] == "respondida" and s["resultado"] == "corregida" and s["respondida_por"] == "aud.ana"
    assert s["respondida_en"] is not None and "informe original" in s["respuesta"]
    assert client.post(responder, json={"resultado": "mantenida", "respuesta": "otra vez"}).status_code == 409
    assert client.post("/pacientes/solicitudes/9999/responder", json={"resultado": "mantenida", "respuesta": "x"}).status_code == 404
    assert client.get("/documentos/REC-1").json()["solicitud_titular"] is None  # ya no está pendiente


def test_el_listado_trae_las_pendientes_por_vencimiento_con_el_nombre_del_paciente(client, llm_falso):
    ficha = ficha_de_ana(client, llm_falso)
    primera = registrar(client, ficha["id"]).json()
    segunda = registrar(client, ficha["id"], documento_id="REC-2").json()
    client.post(f"/pacientes/solicitudes/{segunda['id']}/responder", json={"resultado": "mantenida", "respuesta": "la prioridad corresponde"})

    pendientes = client.get("/pacientes/solicitudes").json()
    assert [s["id"] for s in pendientes] == [primera["id"]]
    assert pendientes[0]["paciente_nombre"] == "Ana María Pérez" and pendientes[0]["documento_id"] == "REC-1"
    assert [s["id"] for s in client.get("/pacientes/solicitudes", params={"estado": "respondida"}).json()] == [segunda["id"]]
    assert len(client.get("/pacientes/solicitudes", params={"estado": "todas"}).json()) == 2
    assert client.get("/pacientes/solicitudes", params={"estado": "otra"}).status_code == 422
