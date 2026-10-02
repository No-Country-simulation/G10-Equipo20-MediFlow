"""Memoria del grafo: dónde recuerda LangGraph en qué etapa quedó cada documento.

Las tablas propias siguen siendo la verdad del negocio (RN-I3, RN-G2). El checkpoint solo sirve para
reanudar el ciclo de vida fuera de la petición que lo empezó: reintentos (RN-P2) y revisión humana (RN-I4).
Vive en la misma base PostgreSQL de la instalación; en la suite unitaria, en memoria (RN-U4).
"""
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from app.models.documento import Documento


def hilo(documento: Documento) -> dict:
    """Un hilo por documento y versión: una versión nueva es un ciclo de vida nuevo (RN-O2)."""
    return {"configurable": {"thread_id": f"{documento.documento_id}:v{documento.version}"}}


def crear_memoria(database_url: str) -> BaseCheckpointSaver:
    if not database_url.startswith("postgresql"):
        return InMemorySaver()
    from langgraph.checkpoint.postgres import PostgresSaver  # noqa: PLC0415 - solo con PostgreSQL
    from psycopg.rows import dict_row  # noqa: PLC0415
    from psycopg_pool import ConnectionPool  # noqa: PLC0415

    # SQLAlchemy usa "postgresql+psycopg://"; psycopg quiere la URL sin el dialecto.
    url = "postgresql://" + database_url.split("://", 1)[1]
    pool = ConnectionPool(conninfo=url, kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row, "connect_timeout": 10},
                          timeout=15, open=True)
    pool.wait(timeout=15)  # una base inalcanzable es un error al arrancar, no una espera infinita en la primera petición
    memoria = PostgresSaver(pool)
    memoria.setup()  # crea sus tablas (checkpoints, checkpoint_blobs, checkpoint_writes) fuera de Alembic
    return memoria
