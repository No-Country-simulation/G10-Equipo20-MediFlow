"""Compuerta de calidad (RN-R3): un cambio de modelo, prompt o reglas no sale a producción si empeora los
falsos negativos críticos.

El conjunto de referencia (RN-R2) guarda, por documento corregido, lo que vio el LLM y lo que una persona decidió.
Un falso negativo crítico es un documento que una persona dejó en Crítico y que las reglas, sobre la propuesta
guardada, no llevan a Crítico. La compuerta vuelve a correr las reglas determinísticas (sin LLM) con la
configuración actual y con la propuesta, y dice si aparecen falsos negativos nuevos. Para un cambio de modelo o
de prompt, el script compuerta_calidad vuelve a pedir la propuesta al LLM sobre el texto seudonimizado.
"""
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.models.referencia import CasoReferencia
from app.packs.modelos import PackPais, Umbrales
from app.schemas.propuesta import PropuestaLLM
from app.schemas.resultado import NivelPrioridad as N
from app.services.evaluacion import ContextoEvaluacion, evaluar


@dataclass
class DocumentoReferencia:
    """Un documento del conjunto: la propuesta del LLM (con tokens) y lo que una persona decidió."""

    documento_id: str
    version: int
    canal_origen: str
    pais: str
    texto: str
    propuesta: dict | None
    nivel_esperado: str | None


@dataclass
class ResultadoCompuerta:
    documentos: int = 0
    sin_propuesta: int = 0
    criticos_esperados: int = 0
    falsos_negativos: list[dict] = field(default_factory=list)  # {documento_id, version, esperado, obtenido}

    @property
    def ids(self) -> set[str]:
        return {f"{f['documento_id']}@{f['version']}" for f in self.falsos_negativos}

    def como_dict(self) -> dict:
        return {"documentos": self.documentos, "sin_propuesta": self.sin_propuesta, "criticos_esperados": self.criticos_esperados,
                "falsos_negativos": len(self.falsos_negativos), "detalle": list(self.falsos_negativos)}


def documentos_de(casos: Iterable[CasoReferencia]) -> list[DocumentoReferencia]:
    """Un documento por (id, versión): todos sus casos comparten propuesta y nivel resultante."""
    por_doc: dict[tuple[str, int], DocumentoReferencia] = {}
    for c in casos:
        por_doc[(c.documento_id, c.version)] = DocumentoReferencia(
            documento_id=c.documento_id, version=c.version, canal_origen=c.canal_origen, pais=c.pais,
            texto=c.texto_seudonimizado or "", propuesta=c.propuesta_json, nivel_esperado=c.nivel_resultante,
        )
    return list(por_doc.values())


def evaluar_conjunto(documentos: Iterable[DocumentoReferencia], pack: PackPais, umbrales: Umbrales,
                     propuestas: dict[tuple[str, int], dict] | None = None) -> ResultadoCompuerta:
    """Reglas determinísticas sobre cada propuesta, sin LLM. `propuestas` reemplaza la propuesta guardada (otro modelo o prompt)."""
    resultado = ResultadoCompuerta()
    for d in documentos:
        propuesta = (propuestas or {}).get((d.documento_id, d.version), d.propuesta)
        if not propuesta:
            resultado.sin_propuesta += 1
            continue
        resultado.documentos += 1
        contexto = ContextoEvaluacion(canal_origen=d.canal_origen, pais=d.pais, cobertura_request=None, texto=d.texto)
        obtenido = evaluar(PropuestaLLM.model_validate(propuesta), contexto, pack, umbrales).clasificacion.nivel_prioridad.value
        if d.nivel_esperado == N.CRITICO.value:
            resultado.criticos_esperados += 1
            if obtenido != N.CRITICO.value:
                resultado.falsos_negativos.append({"documento_id": d.documento_id, "version": d.version, "esperado": d.nivel_esperado, "obtenido": obtenido})
    return resultado


def comparar(actual: ResultadoCompuerta, propuesto: ResultadoCompuerta) -> dict:
    """RN-R3: empeora si aparece algún falso negativo crítico que hoy no existe."""
    nuevos = sorted(propuesto.ids - actual.ids)
    return {
        "documentos": propuesto.documentos, "sin_propuesta": propuesto.sin_propuesta, "criticos_esperados": propuesto.criticos_esperados,
        "actual": actual.como_dict(), "propuesto": propuesto.como_dict(),
        "nuevos_falsos_negativos": nuevos, "empeora": bool(nuevos),
    }


def comparar_configuraciones(casos: Iterable[CasoReferencia], actual: tuple[PackPais, Umbrales], propuesta: tuple[PackPais, Umbrales]) -> dict:
    documentos = documentos_de(casos)
    return comparar(evaluar_conjunto(documentos, *actual), evaluar_conjunto(documentos, *propuesta))
