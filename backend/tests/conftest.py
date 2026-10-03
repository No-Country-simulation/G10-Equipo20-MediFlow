"""Fixtures compartidas. RN-U4: las reglas determinísticas se prueban sin OpenAI ni OCI.

La API no tiene modo sin sesión (RN-K5): cada prueba actúa con cuentas reales que inician sesión.
`client` es un auditor clínico (aud.ana), el rol que más hace en la suite; `como(usuario, rol)` abre otra
sesión en otro navegador, y hay una sesión lista por rol: jefe, quimico, autorizador, gestor, admin, servicio.
"""
import os

# La suite unitaria corre sobre SQLite en memoria por velocidad (RN-U4). La base del
# producto es PostgreSQL: con MEDIFLOW_TEST_DATABASE_URL la misma suite corre contra
# un PostgreSQL real (por ejemplo, el servicio db de docker compose).
URL_BD_TESTS = os.environ.get("MEDIFLOW_TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DATABASE_URL", URL_BD_TESTS)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.deps import get_llm, get_memoria, get_session, get_storage  # noqa: E402
from app.core import sesiones  # noqa: E402
from app.core.database import Base, crear_engine  # noqa: E402
from app.core.sesiones import hash_clave  # noqa: E402
from app.main import app  # noqa: E402
from app.models.gobierno import Usuario  # noqa: E402
from app.services.llm import ClienteFalso  # noqa: E402
from app.services.storage import StorageLocal  # noqa: E402
from app.services.usuarios import ServicioUsuarios  # noqa: E402

CLAVE_PRUEBAS = "Prueba.MediFlow.2026"


@pytest.fixture(autouse=True)
def hash_rapido(monkeypatch):
    """El hash de claves es lento a propósito en producción; en la suite basta con que sea el mismo algoritmo."""
    monkeypatch.setattr(sesiones, "ITERACIONES", 1_000)


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


def crear_cuenta(session: Session, usuario: str, rol: str, *, tipo: str = "persona", nombre: str | None = None) -> Usuario:
    """Una cuenta real con clave definitiva, como la dejaría su dueño tras el primer ingreso."""
    existente = ServicioUsuarios(session).buscar(usuario)
    if existente is not None:
        return existente
    cuenta = Usuario(usuario=usuario, nombre=nombre or usuario.replace(".", " ").title(), rol=rol, tipo=tipo, creado_por="pruebas",
                     clave_hash=hash_clave(CLAVE_PRUEBAS), debe_cambiar_clave=False)
    session.add(cuenta)
    session.commit()
    return cuenta


def iniciar_sesion(cliente: TestClient, session: Session, usuario: str, rol: str, *, tipo: str = "persona") -> TestClient:
    crear_cuenta(session, usuario, rol, tipo=tipo)
    r = cliente.post("/auth/ingresar", json={"usuario": usuario, "clave": CLAVE_PRUEBAS})
    assert r.status_code == 200, r.text
    return cliente


@pytest.fixture
def client(session, storage, llm_falso):
    """Sesión de auditor clínico (aud.ana): ingresa documentos, revisa, da acuse y ve pacientes."""
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_llm] = lambda: llm_falso
    memoria = InMemorySaver()  # un hilo por documento y versión, aislado por prueba
    app.dependency_overrides[get_memoria] = lambda: memoria
    with TestClient(app) as cliente:
        yield iniciar_sesion(cliente, session, "aud.ana", "auditor_clinico")
    app.dependency_overrides.clear()


@pytest.fixture
def como(client, session):
    """Otra sesión, en otro navegador, con la cuenta y el rol que se pidan."""
    abiertos: list[TestClient] = []

    def _como(usuario: str, rol: str, *, tipo: str = "persona") -> TestClient:
        cliente = TestClient(app).__enter__()
        abiertos.append(cliente)
        return iniciar_sesion(cliente, session, usuario, rol, tipo=tipo)

    yield _como
    for cliente in abiertos:
        cliente.__exit__(None, None, None)


@pytest.fixture
def anonimo(client):
    """Un navegador sin sesión contra la misma instalación."""
    with TestClient(app) as otro:
        yield otro


@pytest.fixture
def jefe(como):
    return como("jefe.rojas", "jefe_urgencias")


@pytest.fixture
def quimico(como):
    return como("qf.maria", "quimico_farmaceutico")


@pytest.fixture
def quimico2(como):
    return como("qf.pedro", "quimico_farmaceutico")


@pytest.fixture
def autorizador(como):
    return como("aut.luis", "auditor_autorizaciones")


@pytest.fixture
def gestor(como):
    return como("gestor.ana", "gestor")


@pytest.fixture
def gestor2(como):
    return como("gestor.luis", "gestor")


@pytest.fixture
def admin(como):
    return como("admin.root", "administrador")


@pytest.fixture
def servicio(como):
    """Cuenta de servicio (integración): puede ingresar documentos, nunca una acción clínica (RN-K5)."""
    return como("bot.integracion", "auditor_clinico", tipo="servicio")
