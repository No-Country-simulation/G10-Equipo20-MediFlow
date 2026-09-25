"""Fixtures compartidas. RN-U4: las reglas determinísticas se prueban sin OpenAI ni OCI."""
import os

# La suite unitaria corre sobre SQLite en memoria por velocidad (RN-U4). La base del
# producto es PostgreSQL: con MEDIFLOW_TEST_DATABASE_URL la misma suite corre contra
# un PostgreSQL real (por ejemplo, el servicio db de docker compose).
URL_BD_TESTS = os.environ.get("MEDIFLOW_TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DATABASE_URL", URL_BD_TESTS)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.deps import get_llm, get_session, get_storage
from app.core.database import Base, crear_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.llm import ClienteFalso  # noqa: E402
from app.services.storage import StorageLocal  # noqa: E402


@pytest.fixture
def engine():
    motor = crear_engine(URL_BD_TESTS)
    Base.metadata.drop_all(motor)
    Base.metadata.create_all(motor)
    yield motor
    Base.metadata.drop_all(motor)
    motor.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as sesion:
        yield sesion


@pytest.fixture
def storage(tmp_path):
    return StorageLocal(tmp_path / "bucket")


@pytest.fixture
def llm_falso():
    """RN-U4: la API se prueba sin OpenAI. Cada test agrega las respuestas que espera."""
    return ClienteFalso(respuestas=[], tokens=(100, 50), modelo="falso")


@pytest.fixture
def client(session, storage, llm_falso):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_llm] = lambda: llm_falso
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()
