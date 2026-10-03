"""Directorio de pacientes (RN-M6), conciliación de no identificados (RN-N5) y conflicto de identidad (RN-A4).

El formato de un documento no prueba la identidad: si el mismo número ya está registrado con otro
nombre, el documento clínico no se vincula solo y pasa a revisión humana.
"""
import pytest

from app.services.pacientes import nombres_compatibles
from tests.test_aceptacion import med, receta, TEXTO_ORDEN, TEXTO_RECETA
from tests.test_aceptacion import orden
from tests.test_api_farmacia_autorizaciones import enviar
from tests.test_llm import propuesta_caso_1

TEXTO_SIN_ID = "Fecha: 03/04/2026. Paciente: Carlos Eduardo Mendes, 52 años. TC de tórax normal. Dr. Andrés Rojas, RM 45678."


def informe_sin_id() -> dict:
    p = propuesta_caso_1()
    p["clasificacion"]["nivel_prioridad_propuesto"] = "Rutina"
    p["extraccion"].update({
        "paciente": {"nombre": "[PACIENTE_1]", "edad": 52, "sexo": None, "documento": {"tipo": None, "valor": None}},
        "diagnosticos": [{"texto": "Estudio normal", "cie10_sugerido": "Z00.0", "cie11_sugerido": None}],
        "hallazgos_criticos_detectados": [],
        "signos_vitales": {"FR": 16, "SpO2": 97, "FC": 70, "PAS": 120, "Temp": None, "nivel_conciencia": "alerta"},
    })
    return p


# --- Regla pura: el mismo nombre con más o menos palabras ----------------------------------------


@pytest.mark.parametrize("a, b, compatibles", [
    ("Ana María Pérez", "ANA MARIA PEREZ", True),
    ("Ana María Pérez", "Ana Pérez", True),
    ("Ana Pérez", "Ana María Pérez Gómez", True),
    ("Ana María Pérez", "Luis Castro", False),
    ("Ana Pérez", "Ana Gómez", False),
    ("Ana María Pérez", "María Pérez Ana", True),
])
def test_nombres_compatibles(a, b, compatibles):
    assert nombres_compatibles(a, b) is compatibles


# --- Vínculo ---------------------------------------------------------------------------------


def test_RN_M6_un_documento_enrutado_crea_la_ficha_y_los_siguientes_se_suman(client, llm_falso):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    enviar(client, llm_falso, "REC-2", TEXTO_RECETA.replace("30 (treinta)", "60 (sesenta)"),
           receta([med("losartan", "50 mg", cantidad_numeros="60", cantidad_letras="sesenta")]))
    enviar(client, llm_falso, "ORD-1", TEXTO_ORDEN, orden(), cobertura="contributivo")

    listado = client.get("/pacientes").json()
    assert listado["total"] == 2
    ana = next(p for p in listado["items"] if p["nombre"] == "Ana María Pérez")
    assert ana["tipo_documento"] == "CC" and ana["numero_documento"] == "41234567" and ana["edad"] == 52 and ana["documentos"] == 2  # la edad viene de la propuesta de prueba
    assert client.get("/documentos/REC-1").json()["paciente_id"] == ana["id"]

    ficha = client.get(f"/pacientes/{ana['id']}").json()
    assert [d["documento_id"] for d in ficha["documentos_listado"]] == ["REC-2", "REC-1"]
    assert ficha["documentos_listado"][0]["tipo"] == "Receta Médica" and ficha["documentos_listado"][0]["estado"] == "ENRUTADO"
    assert ficha["historial"] == []

    assert [p["nombre"] for p in client.get("/pacientes", params={"q": "castro"}).json()["items"]] == ["Luis Castro"]
    assert client.get("/pacientes", params={"q": "41234"}).json()["total"] == 1
    assert client.get("/pacientes/9999").status_code == 404


def test_un_documento_en_revision_o_sin_identificador_no_crea_ficha(client, llm_falso):
    p = receta([med("losartan", "50 mg")])
    p["confianzas"]["medicamento_dosis"] = 0.5  # campo dudoso: queda en revisión humana
    enviar(client, llm_falso, "REC-DUDA", TEXTO_RECETA, p)
    enviar(client, llm_falso, "IMG-SIN-ID", TEXTO_SIN_ID, informe_sin_id())
    assert client.get("/documentos/REC-DUDA").json()["estado"] == "EN_REVISION_HUMANA"
    assert client.get("/documentos/IMG-SIN-ID").json()["estado"] == "ENRUTADO"
    assert client.get("/pacientes").json()["total"] == 0
    assert client.get("/documentos/IMG-SIN-ID").json()["paciente_id"] is None


def test_RN_N5_al_resolver_la_revision_el_documento_queda_vinculado(client, llm_falso):
    p = receta([med("losartan", "50 mg")])
    p["confianzas"]["medicamento_dosis"] = 0.5
    enviar(client, llm_falso, "REC-DUDA", TEXTO_RECETA, p)
    r = client.post("/revision/REC-DUDA/resolver", json={"accion": "aprobar", "motivo": "dosis verificada con el original"})
    assert r.status_code == 200, r.text
    paciente = client.get("/pacientes").json()["items"][0]
    assert paciente["nombre"] == "Ana María Pérez"
    assert client.get("/documentos/REC-DUDA").json()["paciente_id"] == paciente["id"]


# --- Conflicto de identidad (RN-A4) --------------------------------------------------------------


def test_RN_A4_el_mismo_documento_con_otro_nombre_va_a_revision_y_no_se_vincula(client, llm_falso):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    suplantado = TEXTO_RECETA.replace("Ana María Pérez", "Rosa Elena Vargas").replace("30 (treinta)", "60 (sesenta)")
    enviar(client, llm_falso, "REC-2", suplantado, receta([med("losartan", "50 mg", cantidad_numeros="60", cantidad_letras="sesenta")]))

    doc = client.get("/documentos/REC-2").json()
    assert doc["estado"] == "EN_REVISION_HUMANA"
    assert doc["resultado"]["evaluacion"]["motivo_auditoria"] == "identidad_en_conflicto"
    assert "paciente.nombre" in doc["resultado"]["evaluacion"]["campos_dudosos"]
    assert doc["paciente_id"] is None
    listado = client.get("/pacientes").json()
    assert listado["total"] == 1 and listado["items"][0]["documentos"] == 1
    conflicto = next(d for d in doc["resultado"]["historial_decisiones"] if d["decision"] == "revision_humana:identidad_en_conflicto")
    assert conflicto["regla"] == "RN-A4" and "Pérez" not in conflicto["evidencia"] and "Vargas" not in conflicto["evidencia"]


def test_RN_A4_corregir_el_numero_resuelve_el_conflicto_y_crea_la_ficha_correcta(client, llm_falso):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    suplantado = TEXTO_RECETA.replace("Ana María Pérez", "Rosa Elena Vargas").replace("30 (treinta)", "60 (sesenta)")
    enviar(client, llm_falso, "REC-2", suplantado, receta([med("losartan", "50 mg", cantidad_numeros="60", cantidad_letras="sesenta")]))
    r = client.post("/revision/REC-2/resolver", json={"accion": "corregir", "motivo": "número mal digitado; el original dice 52.345.678",
                                                      "correcciones": {"extraccion.paciente.documento.valor": "52345678"}})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ENRUTADO"
    nombres = {p["numero_documento"]: p["nombre"] for p in client.get("/pacientes").json()["items"]}
    assert nombres == {"41234567": "Ana María Pérez", "52345678": "Rosa Elena Vargas"}


def test_RN_A4_aprobar_sin_resolver_el_conflicto_entrega_pero_no_vincula(client, llm_falso):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    suplantado = TEXTO_RECETA.replace("Ana María Pérez", "Rosa Elena Vargas").replace("30 (treinta)", "60 (sesenta)")
    enviar(client, llm_falso, "REC-2", suplantado, receta([med("losartan", "50 mg", cantidad_numeros="60", cantidad_letras="sesenta")]))
    r = client.post("/revision/REC-2/resolver", json={"accion": "aprobar", "motivo": "se entrega; identidad por aclarar con admisiones"})
    assert r.status_code == 200 and r.json()["estado"] == "ENRUTADO"
    doc = client.get("/documentos/REC-2").json()
    assert doc["paciente_id"] is None
    assert any(d["decision"] == "documento sin vincular" for d in doc["resultado"]["historial_decisiones"])
    assert client.get("/pacientes").json()["total"] == 1


# --- Edición con rastro (RN-G4, RN-K2) -----------------------------------------------------------


def test_RN_G4_corregir_el_nombre_de_la_ficha_deja_rastro_y_destraba_el_conflicto(client, llm_falso):
    mal_escrito = TEXTO_RECETA.replace("Ana María Pérez", "Ana Maria Peres")
    enviar(client, llm_falso, "REC-1", mal_escrito, receta([med("losartan", "50 mg")]))
    enviar(client, llm_falso, "REC-2", TEXTO_RECETA.replace("30 (treinta)", "60 (sesenta)"),
           receta([med("losartan", "50 mg", cantidad_numeros="60", cantidad_letras="sesenta")]))
    assert client.get("/documentos/REC-2").json()["resultado"]["evaluacion"]["motivo_auditoria"] == "identidad_en_conflicto"
    ficha = client.get("/pacientes").json()["items"][0]

    r = client.patch(f"/pacientes/{ficha['id']}", json={"nombre": "Ana María Pérez", "motivo": "apellido mal digitado en admisión"})
    assert r.status_code == 200, r.text
    rastro = r.json()["historial"]
    assert len(rastro) == 1 and rastro[0]["usuario"] == "aud.ana" and rastro[0]["motivo"] == "apellido mal digitado en admisión"
    assert rastro[0]["anterior"] == {"nombre": "Ana Maria Peres"} and rastro[0]["nuevo"] == {"nombre": "Ana María Pérez"}

    client.post("/revision/REC-2/resolver", json={"accion": "aprobar", "motivo": "nombre corregido en la ficha"})
    assert client.get("/documentos/REC-2").json()["paciente_id"] == ficha["id"]
    assert client.get(f"/pacientes/{ficha['id']}").json()["documentos"] == 2


def test_la_edicion_exige_motivo_rol_clinico_y_no_cambia_el_documento_de_identidad(client, llm_falso, gestor):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    pid = client.get("/pacientes").json()["items"][0]["id"]
    sin_motivo = client.patch(f"/pacientes/{pid}", json={"edad": 59})
    assert sin_motivo.status_code == 422 and "RN-G4" in sin_motivo.json()["detail"]
    otro_rol = gestor.patch(f"/pacientes/{pid}", json={"edad": 59, "motivo": "x"})
    assert otro_rol.status_code == 403 and "RN-K2" in otro_rol.json()["detail"]
    assert client.patch(f"/pacientes/{pid}", json={"numero_documento": "1", "motivo": "x"}).status_code == 422
    assert client.patch(f"/pacientes/{pid}", json={"nombre": "  ", "motivo": "x"}).status_code == 422
    assert client.patch("/pacientes/9999", json={"edad": 59, "motivo": "x"}).status_code == 404
    ok = client.patch(f"/pacientes/{pid}", json={"edad": 59, "motivo": "cumplió años"})
    assert ok.status_code == 200 and ok.json()["edad"] == 59
    assert client.get(f"/pacientes/{pid}").json()["historial"][0]["nuevo"] == {"edad": 59}


def test_RN_K2_otro_rol_clinico_no_edita_pacientes(client, llm_falso, quimico):
    enviar(client, llm_falso, "REC-1", TEXTO_RECETA, receta([med("losartan", "50 mg")]))
    pid = client.get("/pacientes").json()["items"][0]["id"]
    r = quimico.patch(f"/pacientes/{pid}", json={"edad": 59, "motivo": "x"})
    assert r.status_code == 403 and "RN-K2" in r.json()["detail"]
