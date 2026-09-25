"""Conexión a la base de datos. En producción PostgreSQL; en tests SQLite en memoria."""
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def crear_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, pool_pre_ping=True)


@lru_cache
def get_engine() -> Engine:
    return crear_engine(get_settings().database_url)


def crear_tablas() -> None:
    # Importa los modelos para que queden registrados en Base.metadata.
    import app.models  # noqa: F401

    Base.metadata.create_all(get_engine())


def abrir_sesion() -> Iterator[Session]:
    with Session(get_engine()) as sesion:
        yield sesion
