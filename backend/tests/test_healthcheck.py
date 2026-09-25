"""Paso 2: esqueleto del backend.

RN-S2: la instalación opera con un país por defecto (CO).
RN-G6: cada resultado registra el pack y la versión de reglas.
El healthcheck expone ambos para que el operador confirme la instalación.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthcheck_responde_200():
    respuesta = client.get("/health")
    assert respuesta.status_code == 200


def test_healthcheck_declara_pack_y_version_de_reglas():
    cuerpo = client.get("/health").json()
    assert cuerpo["status"] == "ok"
    assert cuerpo["pack_pais"] == "CO"
    assert cuerpo["version_reglas"] == "8"
