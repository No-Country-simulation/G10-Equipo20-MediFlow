"""Paso 5: ciclo de vida del documento (sección 3, reglas RN-I)."""
import pytest

from app.schemas.resultado import EstadoDocumento as E
from app.services.ciclo_vida import (
    ESTADOS_FINALES,
    TransicionInvalida,
    prefijo_storage,
    validar_transicion,
)


@pytest.mark.parametrize(
    "de, a",
    [
        (E.RECIBIDO, E.VALIDADO),
        (E.RECIBIDO, E.RECHAZADO),
        (E.VALIDADO, E.CLASIFICADO),
        (E.CLASIFICADO, E.EXTRAIDO),
        (E.EXTRAIDO, E.EVALUADO),
        (E.EVALUADO, E.ENRUTADO),
        (E.EVALUADO, E.EN_REVISION_HUMANA),
        (E.EN_REVISION_HUMANA, E.RESUELTO),
        (E.RESUELTO, E.ENRUTADO),
        (E.RESUELTO, E.EVALUADO),  # RN-J4: tras corregir se re-ejecutan las reglas
        (E.ENRUTADO, E.ENTREGADO),
        (E.VALIDADO, E.FALLO_TECNICO),
        (E.FALLO_TECNICO, E.VALIDADO),  # reintento vuelve donde estaba
        (E.FALLO_TECNICO, E.EN_REVISION_HUMANA),  # RN-P2: reintentos agotados
    ],
)
def test_transiciones_permitidas(de, a):
    validar_transicion(de, a, motivo="test")


def test_solo_entregado_y_rechazado_son_finales_RN_I1():
    assert ESTADOS_FINALES == {E.ENTREGADO, E.RECHAZADO}


@pytest.mark.parametrize("final", [E.ENTREGADO, E.RECHAZADO])
@pytest.mark.parametrize("destino", list(E))
def test_estados_finales_son_inmutables_RN_I1(final, destino):
    with pytest.raises(TransicionInvalida):
        validar_transicion(final, destino, motivo="test")


@pytest.mark.parametrize(
    "de, a",
    [
        (E.RECIBIDO, E.CLASIFICADO),
        (E.VALIDADO, E.EVALUADO),
        (E.VALIDADO, E.ENRUTADO),
        (E.EXTRAIDO, E.ENRUTADO),
        (E.CLASIFICADO, E.ENTREGADO),
    ],
)
def test_no_se_saltan_etapas_RN_I2(de, a):
    with pytest.raises(TransicionInvalida):
        validar_transicion(de, a, motivo="test")


@pytest.mark.parametrize("de", [E.VALIDADO, E.CLASIFICADO, E.EXTRAIDO, E.EVALUADO, E.ENRUTADO, E.RESUELTO])
def test_el_sistema_solo_rechaza_desde_recibido_RN_I5(de):
    with pytest.raises(TransicionInvalida):
        validar_transicion(de, E.RECHAZADO, motivo="test")


def test_un_revisor_puede_rechazar_con_motivo_RN_I5():
    validar_transicion(E.EN_REVISION_HUMANA, E.RECHAZADO, motivo="documento ilegible")
    with pytest.raises(TransicionInvalida, match="motivo"):
        validar_transicion(E.EN_REVISION_HUMANA, E.RECHAZADO, motivo="")


def test_revision_humana_solo_se_resuelve_por_una_persona_RN_I4():
    with pytest.raises(TransicionInvalida):
        validar_transicion(E.EN_REVISION_HUMANA, E.ENRUTADO, motivo="test")


def test_toda_transicion_exige_motivo_RN_I3():
    with pytest.raises(TransicionInvalida, match="motivo"):
        validar_transicion(E.RECIBIDO, E.VALIDADO, motivo="   ")


def test_prefijo_storage_por_estado_seccion_3_1():
    assert prefijo_storage(E.RECIBIDO, "CO") == "co/recibidos"
    assert prefijo_storage(E.EVALUADO, "CO") == "co/recibidos"
    assert prefijo_storage(E.EN_REVISION_HUMANA, "CO") == "co/auditoria_humana"
    assert prefijo_storage(E.RESUELTO, "CO") == "co/auditoria_humana"
    assert prefijo_storage(E.ENRUTADO, "CO", nivel="Crítico") == "co/procesados/criticos"
    assert prefijo_storage(E.ENTREGADO, "CO", nivel="Urgente") == "co/procesados/urgentes"
    assert prefijo_storage(E.ENTREGADO, "CO", nivel="Rutina") == "co/procesados/rutina"
    assert prefijo_storage(E.RECHAZADO, "CO") == "co/rechazados"
    assert prefijo_storage(E.FALLO_TECNICO, "CO") is None
