"""Paso 4: fechas del pack Colombia (RN-C8, RN-CO11)."""
from datetime import date

import pytest

from app.packs.fechas import formatear_fecha, parsear_fecha
from app.packs.loader import cargar_pack

PACK = cargar_pack("CO")


def test_caso_26_03_04_2026_es_3_de_abril():
    assert parsear_fecha("03/04/2026", PACK) == date(2026, 4, 3)


def test_nunca_se_lee_como_4_de_marzo_RN_CO11():
    assert parsear_fecha("03/04/2026", PACK) != date(2026, 3, 4)


@pytest.mark.parametrize("texto", ["03-04-2026", "3/4/2026", "03.04.2026"])
def test_acepta_variantes_de_separador(texto):
    assert parsear_fecha(texto, PACK) == date(2026, 4, 3)


def test_iso_es_inequivoca_y_se_acepta():
    assert parsear_fecha("2026-04-03", PACK) == date(2026, 4, 3)


@pytest.mark.parametrize("texto", ["04/13/2026", "31/02/2026", "abril 3", "", None])
def test_fecha_imposible_o_ilegible_devuelve_None_RN_C8(texto):
    assert parsear_fecha(texto, PACK) is None


def test_formatear_fecha_usa_dd_mm_aaaa():
    assert formatear_fecha(date(2026, 4, 3), PACK) == "03/04/2026"
