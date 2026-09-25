"""Identidad del paciente (RN-A4, RN-CO1, RN-CO2, RN-CO3) y NIT (RN-CO4).

Ninguna función de este módulo usa el LLM: son reglas determinísticas del pack.
"""
import re
from dataclasses import dataclass

from app.packs.modelos import PackPais
from app.schemas.resultado import EstadoIdentidad

_SEPARADORES_DOCUMENTO = re.compile(r"[.\s]")
_SEPARADORES_NIT = re.compile(r"[.\s]")
# Pesos del algoritmo módulo 11 de la DIAN, de derecha a izquierda.
_PESOS_NIT = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)


@dataclass
class ResultadoIdentidad:
    tipo: str | None
    valor_normalizado: str | None
    estado: EstadoIdentidad
    coherente_con_edad: bool | None = None  # None: no se evaluó (extranjero, sin edad o sin documento)
    formato_por_confirmar: bool = False
    identificador_temporal: str | None = None
    motivo: str | None = None

    @property
    def bloquea_triaje(self) -> bool:
        # RN-A4, RN-N3: la identidad nunca bloquea el triaje ni la alerta crítica.
        return False

    @property
    def retiene_hce(self) -> bool:
        # RN-A4: ausente retiene solo la entrega a Historia Clínica. RN-CO3: igual para MS y AS.
        return self.estado is EstadoIdentidad.AUSENTE

    @property
    def requiere_revision_humana(self) -> bool:
        # RN-A4: invalido va a revisión humana. RN-CO2: una contradicción con la edad también.
        return self.estado is EstadoIdentidad.INVALIDO or self.coherente_con_edad is False


def _normalizar(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpio = _SEPARADORES_DOCUMENTO.sub("", valor.strip())
    return limpio or None


def _coherencia_con_edad(tipo: str, edad: int | None, pack: PackPais) -> bool | None:
    """RN-CO2: RC menor de 7, TI de 7 a 17, CC desde 18, con tolerancia de un año."""
    definicion = pack.identidad_paciente.tipos[tipo]
    rango = pack.identidad_paciente.rangos_edad.get(tipo)
    if not definicion.nacional or rango is None or edad is None:
        return None
    tolerancia = pack.identidad_paciente.tolerancia_edad_anios
    minimo = rango.edad_min - tolerancia
    maximo = float("inf") if rango.edad_max is None else rango.edad_max + tolerancia
    return minimo <= edad <= maximo


def validar_identidad_paciente(
    tipo: str | None,
    valor: str | None,
    *,
    edad: int | None,
    pack: PackPais,
    secuencia: int = 1,
) -> ResultadoIdentidad:
    tipo_norm = tipo.strip().upper() if tipo else None
    tipos = pack.identidad_paciente.tipos

    # RN-A4: sin identificador, el estado es ausente.
    if tipo_norm in (None, "AUSENTE"):
        return ResultadoIdentidad(None, None, EstadoIdentidad.AUSENTE)

    if tipo_norm not in tipos:
        return ResultadoIdentidad(tipo_norm, _normalizar(valor), EstadoIdentidad.INVALIDO, motivo="identidad_invalida")

    definicion = tipos[tipo_norm]

    # RN-CO3: MS y AS equivalen a paciente no identificado con identificador temporal.
    if definicion.no_identificado:
        return ResultadoIdentidad(
            tipo_norm, None, EstadoIdentidad.AUSENTE, identificador_temporal=f"{tipo_norm}-TMP-{secuencia:04d}"
        )

    valor_norm = _normalizar(valor)
    if valor_norm is None:
        return ResultadoIdentidad(tipo_norm, None, EstadoIdentidad.AUSENTE)

    # RN-CO1: sin dígito verificador, el máximo es valido_formato. Patrón None: solo presencia.
    cumple_formato = definicion.patron is None or re.fullmatch(definicion.patron, valor_norm) is not None
    if not cumple_formato:
        return ResultadoIdentidad(tipo_norm, valor_norm, EstadoIdentidad.INVALIDO, motivo="identidad_invalida")

    resultado = ResultadoIdentidad(
        tipo_norm,
        valor_norm,
        EstadoIdentidad.VALIDO_FORMATO,
        formato_por_confirmar=definicion.estado == "por_confirmar",
    )
    resultado.coherente_con_edad = _coherencia_con_edad(tipo_norm, edad, pack)
    if resultado.coherente_con_edad is False:
        resultado.motivo = "ambiguo"
    return resultado


def _digito_verificador_nit(base: str) -> int:
    suma = sum(int(digito) * peso for digito, peso in zip(reversed(base), _PESOS_NIT))
    residuo = suma % 11
    return residuo if residuo in (0, 1) else 11 - residuo


def validar_nit(nit: str | None) -> EstadoIdentidad:
    """RN-CO4: NIT del prestador o la EPS con dígito verificador (módulo 11 DIAN).

    Acepta "800.197.268-4", "800197268-4" y "8001972684". Sin dígito verificador
    reconocible, es inválido.
    """
    if not nit:
        return EstadoIdentidad.INVALIDO
    limpio = _SEPARADORES_NIT.sub("", nit.strip())
    if "-" in limpio:
        base, _, dv = limpio.partition("-")
    else:
        base, dv = limpio[:-1], limpio[-1:]
    if not (base.isdigit() and dv.isdigit() and len(dv) == 1 and 5 <= len(base) <= len(_PESOS_NIT)):
        return EstadoIdentidad.INVALIDO
    if _digito_verificador_nit(base) != int(dv):
        return EstadoIdentidad.INVALIDO
    return EstadoIdentidad.VALIDO_VERIFICADO
