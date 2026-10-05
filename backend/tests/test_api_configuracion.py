"""Fase D: gobierno de la configuración (RN-L1 a RN-L6) y separación de funciones (RN-K2).

Todo corre sin OpenAI (RN-U4): el LLM falso devuelve la propuesta que cada test prepara.
"""
import pytest

from app.packs.loader import cargar_pack, cargar_umbrales
from app.services.configuracion import CambiosConfiguracion, ErrorConfiguracion, aplicar_pack, aplicar_umbrales, toca_seguridad
from app.services.configuracion import acumular, validar_destinos
from tests.test_aceptacion import med, receta, TEXTO_RECETA
from tests.test_api_farmacia_autorizaciones import enviar

GESTOR = {"usuario": "gestor.ana", "rol": "gestor"}


def proponer(client, cambios, motivo="ajuste", **actor):
    cuerpo = {"cambios": cambios, "motivo": motivo, **(GESTOR | actor)}
    return client.post("/configuracion/propuestas", json=cuerpo)


# --- Reglas puras: rangos, no configurables, solo ampliables ---------------------------------


def test_RN_L1_umbral_dentro_de_rango_se_aplica_y_fuera_de_rango_se_rechaza():
    base = cargar_umbrales()
    nuevos = aplicar_umbrales(base, CambiosConfiguracion(umbrales={"confianza.medicamento_dosis": 0.98}))
    assert nuevos.confianza.medicamento_dosis == 0.98
    assert base.confianza.medicamento_dosis == 0.95  # el base no se muta
    with pytest.raises(ErrorConfiguracion) as error:
        aplicar_umbrales(base, CambiosConfiguracion(umbrales={"confianza.medicamento_dosis": 0.50}))
    assert "RN-L1" in str(error.value)


def test_RN_L1_bordes_del_rango(client):
    """RN-U3: el valor que pasa y el inmediato que no."""
    rangos = client.get("/configuracion").json()["rangos"]
    r = rangos["confianza.medicamento_dosis"]
    base = cargar_umbrales()
    assert aplicar_umbrales(base, CambiosConfiguracion(umbrales={"confianza.medicamento_dosis": r["max"]})).confianza.medicamento_dosis == r["max"]
    with pytest.raises(ErrorConfiguracion):
        aplicar_umbrales(base, CambiosConfiguracion(umbrales={"confianza.medicamento_dosis": round(r["max"] + 0.001, 3)}))
    with pytest.raises(ErrorConfiguracion):
        aplicar_umbrales(base, CambiosConfiguracion(umbrales={"confianza.medicamento_dosis": round(r["min"] - 0.001, 3)}))


def test_RN_D1_comunicacion_de_critico_solo_a_la_baja():
    base = cargar_umbrales()
    assert aplicar_umbrales(base, CambiosConfiguracion(umbrales={"tiempos.comunicacion_critico_min": 30})).tiempos.comunicacion_critico_min == 30
    with pytest.raises(ErrorConfiguracion) as error:
        aplicar_umbrales(base, CambiosConfiguracion(umbrales={"tiempos.comunicacion_critico_min": 61}))
    assert "solo a la baja" in str(error.value)


def test_RN_L2_news2_seudonimizacion_y_separacion_no_son_configurables():
    base = cargar_umbrales()
    for clave in ("news2.total_critico", "news2.edad_minima", "seudonimizacion.activa", "separacion_funciones"):
        with pytest.raises(ErrorConfiguracion) as error:
            aplicar_umbrales(base, CambiosConfiguracion(umbrales={clave: 1}))
        assert "RN-L2" in str(error.value), clave


def test_RN_L3_las_listas_solo_se_amplian():
    pack = cargar_pack("CO")
    ampliado = aplicar_pack(pack, CambiosConfiguracion(ampliaciones={"alto_riesgo": ["atorvastatina"], "control_especial": ["tramadol"],
                                                                        "hallazgos_criticos": [{"concepto": "TAPONAMIENTO_CARDIACO", "sinonimos": ["taponamiento cardiaco"], "cie10": ["I31.9"]}]}))
    assert set(pack.medicamentos.alto_riesgo) <= set(ampliado.medicamentos.alto_riesgo)
    assert "atorvastatina" in ampliado.medicamentos.alto_riesgo and "tramadol" in ampliado.medicamentos.control_especial
    assert {h.concepto for h in pack.hallazgos_criticos} <= {h.concepto for h in ampliado.hallazgos_criticos}
    assert "TAPONAMIENTO_CARDIACO" in {h.concepto for h in ampliado.hallazgos_criticos}
    # no existe forma de quitar: el esquema rechaza cualquier clave que no sea una ampliación
    with pytest.raises(Exception):
        CambiosConfiguracion(ampliaciones={"quitar_alto_riesgo": ["apixaban"]})


def test_RN_L5_bajar_confianza_o_alargar_tiempos_toca_seguridad():
    base = cargar_umbrales()
    assert toca_seguridad(base, CambiosConfiguracion(umbrales={"confianza.medicamento_dosis": 0.90})) is True
    assert toca_seguridad(base, CambiosConfiguracion(umbrales={"tiempos.escalamiento_sin_acuse_min": 20})) is True
    assert toca_seguridad(base, CambiosConfiguracion(umbrales={"consistencia.tolerancia_edad_anios": 2})) is True
    assert toca_seguridad(base, CambiosConfiguracion(umbrales={"confianza.medicamento_dosis": 0.98})) is False
    assert toca_seguridad(base, CambiosConfiguracion(umbrales={"tiempos.escalamiento_sin_acuse_min": 10})) is False
    assert toca_seguridad(base, CambiosConfiguracion(ampliaciones={"alto_riesgo": ["atorvastatina"]})) is False


# --- API -----------------------------------------------------------------------------------------


def test_configuracion_expone_vigente_base_rangos_y_listas(client):
    r = client.get("/configuracion")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["vigente"]["numero"] == 0 and cuerpo["vigente"]["autor"] == "sistema"
    assert cuerpo["umbrales_efectivos"]["confianza"]["medicamento_dosis"] == 0.95
    assert cuerpo["rangos"]["confianza.clasificacion"]["min"] <= 0.85 <= cuerpo["rangos"]["confianza.clasificacion"]["max"]
    assert cuerpo["rangos"]["tiempos.comunicacion_critico_min"]["solo_a_la_baja"] is True
    assert cuerpo["no_configurable"]["news2"]["total_critico"] == 7  # RN-L2: visible, no editable
    assert "apixaban" in cuerpo["listas"]["alto_riesgo"]["base"]
    assert cuerpo["listas"]["alto_riesgo"]["ampliadas"] == []
    assert cuerpo["propuestas"] == [] and cuerpo["historial"] == []


def test_RN_L6_simulacion_muestra_que_habria_cambiado_sobre_los_ultimos_documentos(client, llm_falso):
    from app.services.llm import ErrorTransitorioLLM

    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))  # confianza 0.97 -> ENRUTADO
    llm_falso.respuestas.extend([ErrorTransitorioLLM("sin clave")] * 3)  # RN-P2: agota reintentos, queda sin propuesta
    client.post("/documentos", json={"documento_id": "FALLO-1", "canal_origen": "Consulta_Ambulatoria", "tipo_contenido": "texto",
                                     "contenido_texto": "Fecha: 03/04/2026. Texto sin propuesta. Dr. Rojas RM 1."})
    assert client.get("/documentos/REC-1").json()["estado"] == "ENRUTADO"
    r = client.post("/configuracion/simular", json={"cambios": {"umbrales": {"confianza.medicamento_dosis": 0.98}}, "ultimos": 50})
    assert r.status_code == 200, r.text
    sim = r.json()
    assert sim["documentos_evaluados"] == 1 and sim["sin_propuesta"] == 1 and sim["cambian"] == 1
    fila = sim["detalle"][0]
    assert fila["documento_id"] == "REC-1"
    assert fila["estado_actual"] == "ENRUTADO" and fila["estado_simulado"] == "EN_REVISION_HUMANA"
    assert fila["motivo_simulado"] == "campo_dudoso"
    assert "Pérez" not in r.text  # RN-M4
    # nada cambió de verdad
    assert client.get("/documentos/REC-1").json()["estado"] == "ENRUTADO"
    assert client.get("/configuracion").json()["umbrales_efectivos"]["confianza"]["medicamento_dosis"] == 0.95


def test_RN_L4_una_propuesta_aprobada_es_version_nueva_con_autor_fecha_y_vigencia_y_no_es_retroactiva(client, llm_falso):
    enviar(client, llm_falso, "REC-ANTES", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    r = proponer(client, {"umbrales": {"confianza.medicamento_dosis": 0.98}}, motivo="cero errores de dosis (sección 8)")
    assert r.status_code == 201, r.text
    propuesta = r.json()
    assert propuesta["estado"] == "propuesta" and propuesta["toca_seguridad"] is False and propuesta["aprobaciones_requeridas"] == 1
    assert propuesta["simulacion"]["cambian"] == 1  # RN-L6: la simulación acompaña a la propuesta
    aprobada = client.post(f"/configuracion/propuestas/{propuesta['id']}/aprobar", json=GESTOR)
    assert aprobada.status_code == 200, aprobada.text
    assert aprobada.json()["estado"] == "vigente"

    cfg = client.get("/configuracion").json()
    assert cfg["vigente"]["numero"] == 1 and cfg["vigente"]["autor"] == "gestor.ana" and cfg["vigente"]["vigente_desde"]
    assert cfg["umbrales_efectivos"]["confianza"]["medicamento_dosis"] == 0.98
    assert cfg["historial"][0]["numero"] == 1 and cfg["historial"][0]["estado"] == "vigente"

    # RN-L4: lo ya procesado no cambia; lo nuevo sigue la configuración vigente
    assert client.get("/documentos/REC-ANTES").json()["estado"] == "ENRUTADO"
    enviar(client, llm_falso, "REC-DESPUES", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    despues = client.get("/documentos/REC-DESPUES").json()
    assert despues["estado"] == "EN_REVISION_HUMANA"
    assert despues["resultado"]["evaluacion"]["motivo_auditoria"] == "campo_dudoso"
    assert despues["umbrales"]["medicamento_dosis"] == 0.98


def test_RN_L5_un_cambio_que_toca_seguridad_exige_dos_aprobadores_distintos(client):
    r = proponer(client, {"umbrales": {"confianza.medicamento_dosis": 0.90}}, motivo="menos revisión")
    assert r.status_code == 201, r.text
    propuesta = r.json()
    assert propuesta["toca_seguridad"] is True and propuesta["aprobaciones_requeridas"] == 2
    primera = client.post(f"/configuracion/propuestas/{propuesta['id']}/aprobar", json=GESTOR)
    assert primera.status_code == 200 and primera.json()["estado"] == "propuesta"
    assert client.get("/configuracion").json()["umbrales_efectivos"]["confianza"]["medicamento_dosis"] == 0.95
    repetida = client.post(f"/configuracion/propuestas/{propuesta['id']}/aprobar", json=GESTOR)
    assert repetida.status_code == 409 and "RN-L5" in repetida.json()["detail"]
    segunda = client.post(f"/configuracion/propuestas/{propuesta['id']}/aprobar", json={"usuario": "gestor.luis", "rol": "gestor"})
    assert segunda.status_code == 200 and segunda.json()["estado"] == "vigente"
    assert [a["usuario"] for a in segunda.json()["aprobaciones"]] == ["gestor.ana", "gestor.luis"]
    assert client.get("/configuracion").json()["umbrales_efectivos"]["confianza"]["medicamento_dosis"] == 0.90


def test_RN_L3_ampliar_alto_riesgo_cambia_la_doble_verificacion_de_las_recetas_nuevas(client, llm_falso):
    r = proponer(client, {"ampliaciones": {"alto_riesgo": ["atorvastatina"]}}, motivo="protocolo interno")
    assert r.status_code == 201, r.text
    assert client.post(f"/configuracion/propuestas/{r.json()['id']}/aprobar", json=GESTOR).json()["estado"] == "vigente"
    listas = client.get("/configuracion").json()["listas"]
    assert listas["alto_riesgo"]["ampliadas"] == ["atorvastatina"] and "apixaban" in listas["alto_riesgo"]["base"]
    enviar(client, llm_falso, "REC-ATV", TEXTO_RECETA.replace("Losartán", "Atorvastatina"), receta([med("atorvastatina", "40 mg")]))
    cola = client.get("/farmacia").json()
    assert cola[0]["documento_id"] == "REC-ATV" and cola[0]["alto_riesgo"] is True and cola[0]["verificaciones_requeridas"] == 2


def test_una_propuesta_reemplaza_a_la_vigente_y_queda_en_el_historial(client):
    primera = proponer(client, {"umbrales": {"confianza.profesional": 0.90}}).json()
    client.post(f"/configuracion/propuestas/{primera['id']}/aprobar", json=GESTOR)
    segunda = proponer(client, {"umbrales": {"confianza.profesional": 0.92}}).json()
    client.post(f"/configuracion/propuestas/{segunda['id']}/aprobar", json=GESTOR)
    cfg = client.get("/configuracion").json()
    assert cfg["vigente"]["numero"] == 2 and cfg["umbrales_efectivos"]["confianza"]["profesional"] == 0.92
    assert [(v["numero"], v["estado"]) for v in cfg["historial"]] == [(2, "vigente"), (1, "reemplazada")]
    assert cfg["historial"][1]["vigente_hasta"]


def test_RN_L3_RN_L4_una_version_posterior_no_deshace_lo_que_cambiaron_las_anteriores(client):
    primera = proponer(client, {"umbrales": {"confianza.medicamento_dosis": 0.98}, "ampliaciones": {"alto_riesgo": ["atorvastatina"]}}).json()
    client.post(f"/configuracion/propuestas/{primera['id']}/aprobar", json=GESTOR)
    segunda = proponer(client, {"umbrales": {"confianza.profesional": 0.92}, "ampliaciones": {"alto_riesgo": ["rosuvastatina"]}}).json()
    client.post(f"/configuracion/propuestas/{segunda['id']}/aprobar", json=GESTOR)
    rechazada = proponer(client, {"umbrales": {"confianza.resto": 0.90}}).json()
    client.post(f"/configuracion/propuestas/{rechazada['id']}/rechazar", json=GESTOR | {"motivo": "no"})
    cfg = client.get("/configuracion").json()
    assert cfg["vigente"]["numero"] == 2
    assert cfg["vigente"]["cambios"]["umbrales"] == {"confianza.profesional": 0.92}  # cada versión guarda solo lo suyo
    efectivos = cfg["umbrales_efectivos"]["confianza"]
    assert efectivos["medicamento_dosis"] == 0.98 and efectivos["profesional"] == 0.92 and efectivos["resto"] == 0.80
    assert cfg["listas"]["alto_riesgo"]["ampliadas"] == ["atorvastatina", "rosuvastatina"]


def test_rechazar_una_propuesta_la_saca_de_pendientes(client):
    p = proponer(client, {"umbrales": {"confianza.profesional": 0.90}}).json()
    assert client.get("/configuracion").json()["propuestas"][0]["id"] == p["id"]
    r = client.post(f"/configuracion/propuestas/{p['id']}/rechazar", json=GESTOR | {"motivo": "sin datos que lo respalden"})
    assert r.status_code == 200 and r.json()["estado"] == "rechazada"
    cfg = client.get("/configuracion").json()
    assert cfg["propuestas"] == [] and cfg["historial"][0]["estado"] == "rechazada"
    assert client.post(f"/configuracion/propuestas/{p['id']}/aprobar", json=GESTOR).status_code == 409


def test_validaciones_de_la_api_citan_la_regla(client):
    assert "RN-L1" in proponer(client, {"umbrales": {"confianza.medicamento_dosis": 0.5}}).json()["detail"]
    assert "RN-L2" in proponer(client, {"umbrales": {"news2.total_critico": 5}}).json()["detail"]
    assert proponer(client, {"umbrales": {}}).status_code == 422  # sin cambios no hay versión
    assert proponer(client, {"umbrales": {"confianza.profesional": 0.9}}, motivo="").status_code == 422  # RN-L4: motivo
    assert client.post("/configuracion/propuestas/999/aprobar", json=GESTOR).status_code == 404


def test_RN_K2_solo_el_gestor_configura(client):
    r = proponer(client, {"umbrales": {"confianza.profesional": 0.9}}, usuario="aud.ana", rol="auditor_clinico")
    assert r.status_code == 403 and "RN-K2" in r.json()["detail"]
    p = proponer(client, {"umbrales": {"confianza.profesional": 0.9}}).json()
    r = client.post(f"/configuracion/propuestas/{p['id']}/aprobar", json={"usuario": "admin.root", "rol": "administrador"})
    assert r.status_code == 403 and "RN-K2" in r.json()["detail"]


# --- Destinos activos (RN-L1) ---------------------------------------------------------------------


def test_RN_L2_emergencia_y_revision_humana_no_se_desactivan():
    for protegido in ("Cola_Emergencia_Medica", "Cola_Revision_Humana"):
        with pytest.raises(ErrorConfiguracion, match="RN-L2"):
            validar_destinos(CambiosConfiguracion(destinos_inactivos=[protegido]))
    validar_destinos(CambiosConfiguracion(destinos_inactivos=["Farmacia_Hospitalaria"]))
    with pytest.raises(ValueError):
        CambiosConfiguracion(destinos_inactivos=["Destino_Inventado"])


def test_RN_L5_desactivar_un_destino_toca_seguridad_y_reactivarlo_no():
    base = cargar_umbrales()
    assert toca_seguridad(base, CambiosConfiguracion(destinos_inactivos=["Farmacia_Hospitalaria"])) is True
    assert toca_seguridad(base, CambiosConfiguracion(destinos_inactivos=[]), ["Farmacia_Hospitalaria"]) is False
    assert toca_seguridad(base, CambiosConfiguracion(destinos_inactivos=["Farmacia_Hospitalaria"]), ["Farmacia_Hospitalaria"]) is False


def test_los_destinos_de_una_version_se_heredan_hasta_que_otra_los_cambia():
    v1 = CambiosConfiguracion(destinos_inactivos=["Farmacia_Hospitalaria"])
    v2 = CambiosConfiguracion(umbrales={"confianza.profesional": 0.9})
    assert [d.value for d in acumular(v1, v2).destinos_inactivos] == ["Farmacia_Hospitalaria"]
    assert acumular(acumular(v1, v2), CambiosConfiguracion(destinos_inactivos=[])).destinos_inactivos == []
    assert aplicar_pack(cargar_pack("CO"), acumular(v1, v2)).destinos_inactivos == ["Farmacia_Hospitalaria"]


def test_RN_L1_el_gestor_desactiva_un_destino_y_lo_nuevo_va_a_revision_humana(client, llm_falso):
    enviar(client, llm_falso, "REC-ANTES", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    cfg = client.get("/configuracion").json()
    assert {d["destino"]: (d["activo"], d["protegido"]) for d in cfg["destinos"]}["Cola_Emergencia_Medica"] == (True, True)
    assert all(d["activo"] for d in cfg["destinos"])

    r = proponer(client, {"destinos_inactivos": ["Farmacia_Hospitalaria"]}, motivo="la sede no tiene farmacia propia")
    assert r.status_code == 201, r.text
    propuesta = r.json()
    assert propuesta["toca_seguridad"] is True and propuesta["aprobaciones_requeridas"] == 2  # RN-L5
    assert propuesta["simulacion"]["mas_a_revision"] == 1  # RN-L6: la receta ya procesada cambiaría
    client.post(f"/configuracion/propuestas/{propuesta['id']}/aprobar", json=GESTOR)
    aprobada = client.post(f"/configuracion/propuestas/{propuesta['id']}/aprobar", json={"usuario": "gestor.luis", "rol": "gestor"})
    assert aprobada.json()["estado"] == "vigente"

    destinos = {d["destino"]: d["activo"] for d in client.get("/configuracion").json()["destinos"]}
    assert destinos["Farmacia_Hospitalaria"] is False and destinos["Historia_Clinica_Electronica"] is True
    assert client.get("/documentos/REC-ANTES").json()["estado"] == "ENRUTADO"  # RN-L4: no es retroactiva
    enviar(client, llm_falso, "REC-DESPUES", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    despues = client.get("/documentos/REC-DESPUES").json()
    assert despues["estado"] == "EN_REVISION_HUMANA"
    assert despues["resultado"]["evaluacion"]["motivo_auditoria"] == "destino_inactivo"
    assert "Farmacia_Hospitalaria" in next(r["detalle"] for r in client.get("/administracion/puesta_en_marcha").json()["requisitos"]
                                           if r["clave"] == "destinos_activos")

    # una versión posterior que no toca destinos los hereda; otra los reactiva con una sola aprobación
    otra = proponer(client, {"umbrales": {"tiempos.escalamiento_sin_acuse_min": 10}}).json()
    client.post(f"/configuracion/propuestas/{otra['id']}/aprobar", json=GESTOR)
    assert {d["destino"]: d["activo"] for d in client.get("/configuracion").json()["destinos"]}["Farmacia_Hospitalaria"] is False
    reactivar = proponer(client, {"destinos_inactivos": []}, motivo="farmacia habilitada").json()
    assert reactivar["toca_seguridad"] is False
    assert client.post(f"/configuracion/propuestas/{reactivar['id']}/aprobar", json=GESTOR).json()["estado"] == "vigente"
    enviar(client, llm_falso, "REC-FINAL", TEXTO_RECETA.replace("30 (treinta)", "60 (sesenta)"), receta([med("losartan", "50 mg", cantidad_numeros="60", cantidad_letras="sesenta")]))
    assert client.get("/documentos/REC-FINAL").json()["estado"] == "ENRUTADO"


def test_RN_L2_la_api_rechaza_desactivar_un_destino_protegido_o_inexistente(client):
    r = proponer(client, {"destinos_inactivos": ["Cola_Emergencia_Medica"]})
    assert r.status_code == 422 and "RN-L2" in r.json()["detail"]
    assert proponer(client, {"destinos_inactivos": ["Destino_Inventado"]}).status_code == 422
    assert all(d["activo"] for d in client.get("/configuracion").json()["destinos"])
