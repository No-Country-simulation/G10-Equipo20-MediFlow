"""Ciclo de vida del documento (sección 3 y reglas RN-I).

Todo documento está en exactamente un estado. Solo ENTREGADO y RECHAZADO son finales.
El desvío por revisión humana siempre vuelve al pipeline, y un fallo técnico nunca
descarta el documento.
"""
from app.schemas.resultado import EstadoDocumento as E

ESTADOS_FINALES: frozenset[E] = frozenset({E.ENTREGADO, E.RECHAZADO})  # RN-I1

_ESTADOS_DE_PROCESO = {E.VALIDADO, E.CLASIFICADO, E.EXTRAIDO, E.EVALUADO, E.ENRUTADO}

TRANSICIONES: dict[E, frozenset[E]] = {
    # RN-I5: el sistema solo rechaza desde RECIBIDO.
    E.RECIBIDO: frozenset({E.VALIDADO, E.RECHAZADO, E.FALLO_TECNICO}),
    E.VALIDADO: frozenset({E.CLASIFICADO, E.FALLO_TECNICO}),
    E.CLASIFICADO: frozenset({E.EXTRAIDO, E.FALLO_TECNICO}),
    E.EXTRAIDO: frozenset({E.EVALUADO, E.FALLO_TECNICO}),
    # RN-I2: nada llega a ENRUTADO sin pasar por EVALUADO.
    E.EVALUADO: frozenset({E.ENRUTADO, E.EN_REVISION_HUMANA, E.FALLO_TECNICO}),
    # RN-I4: bloqueado para el agente; solo una persona lo resuelve o lo rechaza con motivo (RN-I5).
    E.EN_REVISION_HUMANA: frozenset({E.RESUELTO, E.RECHAZADO}),
    # RN-J4: tras una corrección se re-ejecutan las reglas (EVALUADO); si se aprueba, sigue a ENRUTADO.
    E.RESUELTO: frozenset({E.EVALUADO, E.ENRUTADO}),
    E.ENRUTADO: frozenset({E.ENTREGADO, E.FALLO_TECNICO}),
    E.ENTREGADO: frozenset(),
    E.RECHAZADO: frozenset(),
    # Reintento: vuelve al estado donde estaba. RN-P2: reintentos agotados, a revisión humana.
    E.FALLO_TECNICO: frozenset(_ESTADOS_DE_PROCESO | {E.EN_REVISION_HUMANA}),
}


class TransicionInvalida(Exception):
    pass


def validar_transicion(de: E, a: E, *, motivo: str) -> None:
    if not motivo or not motivo.strip():
        raise TransicionInvalida("RN-I3: toda transición registra un motivo")
    if de in ESTADOS_FINALES:
        raise TransicionInvalida(f"RN-I1: {de.value} es final e inmutable")
    if a not in TRANSICIONES[de]:
        raise TransicionInvalida(f"Transición no permitida: {de.value} -> {a.value}")


_CARPETA_NIVEL = {"Crítico": "criticos", "Urgente": "urgentes", "Rutina": "rutina"}


def prefijo_storage(estado: E, pais: str, *, nivel: str | None = None) -> str | None:
    """Ruta en OCI por estado (sección 3.1 y RN-G1). FALLO_TECNICO no cambia la ruta."""
    base = pais.lower()
    if estado in (E.RECIBIDO, E.VALIDADO, E.CLASIFICADO, E.EXTRAIDO, E.EVALUADO):
        return f"{base}/recibidos"
    if estado in (E.EN_REVISION_HUMANA, E.RESUELTO):
        return f"{base}/auditoria_humana"
    if estado in (E.ENRUTADO, E.ENTREGADO):
        if nivel is None:
            raise ValueError("RN-G1: procesados/ se segrega por nivel de prioridad")
        return f"{base}/procesados/{_CARPETA_NIVEL[nivel]}"
    if estado is E.RECHAZADO:
        return f"{base}/rechazados"
    return None
