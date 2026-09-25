"""Fixtures compartidas. RN-U4: las reglas determinísticas se prueban sin OpenAI ni OCI."""
import os

# La app de tests nunca toca PostgreSQL ni OCI (RN-U4). Debe fijarse antes de importar la app.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.deps import get_session, get_storage
from app.core.database import Base, crear_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.storage import StorageLocal  # noqa: E402


@pytest.fixture
def engine():
    motor = crear_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(motor)
    yield motor
    motor.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as sesion:
        yield sesion


@pytest.fixture
def storage(tmp_path):
    return StorageLocal(tmp_path / "bucket")


@pytest.fixture
def client(session, storage):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()
