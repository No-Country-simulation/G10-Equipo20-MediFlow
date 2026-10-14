import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import require_staff
from app.core.database import get_engine, get_session
from app.main import app


@pytest.fixture(scope='session', autouse=True)
def schema():
    command.upgrade(Config('alembic.ini'), 'head')


@pytest.fixture
def session():
    with get_engine().connect() as connection:
        transaction = connection.begin()
        with Session(connection, join_transaction_mode='create_savepoint') as session:
            yield session
        transaction.rollback()


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[require_staff] = lambda: {'id': 'test', 'role': 'SUPERADMIN'}
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
