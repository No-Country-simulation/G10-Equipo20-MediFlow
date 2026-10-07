"""Hallazgos críticos por concepto clínico (RN-D1), detectados por tres vías
independientes (RN-D2): código (CIE-10 o CIE-11, RN-CO6), término textual con
sinónimos del pack, o hallazgo declarado por el LLM. Basta una.

`detectar_en_texto` no depende del LLM: es lo que sigue corriendo cuando OpenAI
está caído (RN-P4) y lo que nunca se detiene por presupuesto (RN-T1).
"""
import re
import unicodedata
from dataclasses import dataclass, field

from app.packs.modelos import HallazgoCritico, PackPais
from app.schemas.propuesta import DiagnosticoPropuesto

_CODIGO_EN_TEXTO = re.compile(r"\b[A-Z][A-Z0-9]\d(?:\.[0-9A-Z]{1,2})?\b")
_SIGNOS_TENSION = ("a tension", "hipertensivo", "en tension", "desviacion mediastinal")

# Un término crítico en contexto histórico o negado no es un hallazgo de hoy: "antecedente de TEP", "se descarta disección",
# "niega infarto". Se mira la misma cláusula (entre puntos, comas o dos puntos). Una "sospecha" sí cuenta: aquí es acción.
_CLAUSULAS = re.compile(r"[.;:,\n()]")
_ANTES_DEL_TERMINO = re.compile(
    r"(?:\b(?:antecedentes?(?: personales| familiares| patologicos)?(?: de)?|historia(?:l)? de|descartad[oa]s?|se descarta|niega|"
    r"ausencia de|no se (?:evidencia|observa|aprecia|documenta|identifica|confirma)|"
    r"sin (?:signos|evidencia|datos|hallazgos|criterios|imagenes) de|no hay (?:signos|evidencia|datos) de)\b(?:\s+\S+){0,3}"
    r"|\b(?:sin|no|no hay))\s+$"
)
_DESPUES_DEL_TERMINO = re.compile(r"^\s+(?:\S+\s+){0,2}?(?:resuelt[oa]s?|descartad[oa]s?|previ[oa]s?|antigu[oa]s?|en el pasado|hace \d+ (?:anos|meses|semanas))\b")


@dataclass
class Deteccion:
    concepto: str
    vias: list[str] = field(default_factory=list)
    evidencias: list[str] = field(default_factory=list)

    @property
    def via(self) -> str:
        return self.vias[0]

    @property
    def evidencia(self) -> str:
        return "; ".join(self.evidencias)


def normalizar(texto: str) -> str:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sin_tildes.lower()).strip()


def _codigo(valor: str | None) -> str | None:
    return valor.strip().upper() if valor else None


def _hay_signos_de_tension(texto_norm: str) -> bool:
    return any(signo in texto_norm for signo in _SIGNOS_TENSION)


def _agregar(detecciones: dict[str, Deteccion], concepto: str, via: str, evidencia: str) -> None:
    det = detecciones.setdefault(concepto, Deteccion(concepto))
    if via not in det.vias:
        det.vias.append(via)
    if evidencia not in det.evidencias:
        det.evidencias.append(evidencia)


def _por_codigo(detecciones: dict[str, Deteccion], hallazgo: HallazgoCritico, codigo: str | None, texto_norm: str, origen: str) -> None:
    if codigo is None or (codigo not in hallazgo.cie10 and codigo not in hallazgo.cie11):
        return
    if hallazgo.requiere_signos_tension and not _hay_signos_de_tension(texto_norm):
        return
    _agregar(detecciones, hallazgo.concepto, "codigo", f"{origen} {codigo}")


def _ocurrencias(texto_norm: str, termino: str) -> tuple[bool, str | None]:
    """(hay una ocurrencia vigente, ejemplo de ocurrencia histórica o negada). Basta una vigente para que el término cuente."""
    historica: str | None = None
    for clausula in _CLAUSULAS.split(texto_norm):
        inicio = clausula.find(termino)
        while inicio >= 0:
            fin = inicio + len(termino)
            if _ANTES_DEL_TERMINO.search(clausula[:inicio]) or _DESPUES_DEL_TERMINO.match(clausula[fin:]):
                historica = historica or clausula.strip()
            else:
                return True, None
            inicio = clausula.find(termino, fin)
    return False, historica


def _detectar_en_texto(detecciones: dict[str, Deteccion], texto: str, pack: PackPais, descartes: list[str] | None = None) -> None:
    if not texto:
        return
    texto_norm = normalizar(texto)
    codigos_en_texto = set(_CODIGO_EN_TEXTO.findall(texto.upper()))
    for hallazgo in pack.hallazgos_criticos:
        for sinonimo in hallazgo.sinonimos:
            vigente, historica = _ocurrencias(texto_norm, normalizar(sinonimo))
            if vigente:
                _agregar(detecciones, hallazgo.concepto, "termino", f"texto contiene '{sinonimo}'")
            elif historica is not None and descartes is not None:
                descartes.append(f"{hallazgo.concepto}: '{sinonimo}' solo en contexto histórico o negado: \"{historica}\"")
        for codigo in codigos_en_texto:
            _por_codigo(detecciones, hallazgo, codigo, texto_norm, "texto contiene código")


def detectar_en_texto(texto: str, pack: PackPais, descartes: list[str] | None = None) -> list[Deteccion]:
    """Detección determinística sobre texto, sin LLM (RN-P4). En `descartes` deja constancia de los términos que aparecieron
    solo como antecedente o negados, para que el historial explique por qué no hubo alerta (RN-G2)."""
    detecciones: dict[str, Deteccion] = {}
    _detectar_en_texto(detecciones, texto, pack, descartes)
    return list(detecciones.values())


def detectar_hallazgos(
    *,
    diagnosticos: list[DiagnosticoPropuesto],
    texto: str,
    declarados: list[str],
    pack: PackPais,
    descartes: list[str] | None = None,
) -> list[Deteccion]:
    detecciones: dict[str, Deteccion] = {}
    texto_norm = normalizar(texto or "")
    conceptos_validos = {h.concepto for h in pack.hallazgos_criticos}

    for hallazgo in pack.hallazgos_criticos:
        for dx in diagnosticos:
            _por_codigo(detecciones, hallazgo, _codigo(dx.cie10_sugerido), texto_norm, "cie10_sugerido")
            _por_codigo(detecciones, hallazgo, _codigo(dx.cie11_sugerido), texto_norm, "cie11_sugerido")

    _detectar_en_texto(detecciones, texto, pack, descartes)

    for concepto in declarados:
        if concepto in conceptos_validos:
            _agregar(detecciones, concepto, "hallazgo_llm", "declarado por el LLM")

    return list(detecciones.values())
