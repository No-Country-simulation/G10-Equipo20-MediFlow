"""Migraciones Alembic (mejora traída de la rama bryan-segovia).

El esquema de PostgreSQL evoluciona con migraciones versionadas, no con create_all.
La suite aplica las migraciones sobre una base vacía y comprueba que el resultado
coincide con los modelos (autogenerate no debe proponer cambios).
"""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

import app.models  # noqa: F401
from app.core.database import Base

BACKEND = Path(__file__).resolve().parents[1]


def configuracion(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    os.environ["DATABASE_URL"] = url
    from app.core.config import get_settings

    get_settings.cache_clear()
    return cfg


@pytest.fixture
def url_sqlite(tmp_path):
    original = os.environ.get("DATABASE_URL")
    yield f"sqlite+pysqlite:///{(tmp_path / 'migraciones.db').as_posix()}"
    from app.core.config import get_settings

    if original is not None:
        os.environ["DATABASE_URL"] = original
    get_settings.cache_clear()


def test_hay_una_sola_cabeza_de_migracion():
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert len(script.get_heads()) == 1


def test_upgrade_head_crea_todas_las_tablas(url_sqlite):
    command.upgrade(configuracion(url_sqlite), "head")
    motor = create_engine(url_sqlite)
    tablas = set(inspect(motor).get_table_names())
    assert {"documentos", "transiciones_estado", "alertas", "correcciones", "alembic_version"} <= tablas
    columnas = {c["name"] for c in inspect(motor).get_columns("documentos")}
    assert {"formato", "num_paginas", "paginas_json", "mapa_reidentificacion", "propuesta_json"} <= columnas
    motor.dispose()


def test_las_migraciones_coinciden_con_los_modelos(url_sqlite):
    command.upgrade(configuracion(url_sqlite), "head")
    motor = create_engine(url_sqlite)
    with motor.connect() as conexion:
        contexto = MigrationContext.configure(conexion, opts={"compare_type": False})
        diferencias = compare_metadata(contexto, Base.metadata)
    motor.dispose()
    assert diferencias == [], diferencias


def test_downgrade_a_base_deja_la_base_vacia(url_sqlite):
    cfg = configuracion(url_sqlite)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    motor = create_engine(url_sqlite)
    assert set(inspect(motor).get_table_names()) <= {"alembic_version"}
    motor.dispose()
