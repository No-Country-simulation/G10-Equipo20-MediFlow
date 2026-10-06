"""Conjunto de referencia seudonimizado (RN-R2).

Cada corrección humana (RN-J8) y cada transcripción (RN-P2) se convierte en un caso: lo que vio el LLM, lo que
propuso, lo que la persona corrigió y la prioridad antes y después. Todo con los tokens de RN-M1: el mapa de
re-identificación se aplica al revés y lo identificante que no estaba en el mapa (un nombre que la persona
escribió) se reemplaza por un token nuevo. El conjunto alimenta la compuerta de calidad de RN-R3.
"""
import re
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alerta import Correccion
from app.models.documento import Documento
from app.models.referencia import CasoReferencia
from app.schemas.resultado import ResultadoTriaje

# Rutas de la propuesta cuyo valor identifica a una persona: nunca viajan en claro al conjunto.
IDENTIFICANTES = {
    "extraccion.paciente.nombre": "PACIENTE", "extraccion.paciente.nome": "PACIENTE", "extraccion.paciente.documento.valor": "ID",
    "extraccion.profesional.nombre": "PROFESIONAL", "extraccion.profesional.numero_documento": "ID",
}
_TOKEN = re.compile(r"^\[[A-Z]+_\d+\]$")


def _ruta_normalizada(ruta: str) -> str:
    """extraccion.medicamentos.0.dosis y extraccion.medicamentos[0].dosis -> extraccion.medicamentos.*.dosis"""
    return re.sub(r"(\.\d+|\[\d+\])(?=\.|$)", ".*", ruta)


class Seudonimo:
    """Aplica el mapa token -> original al revés, y enmascara lo identificante que no estaba en el mapa."""

    def __init__(self, mapa: dict[str, str] | None):
        self.inverso = sorted(((original, token) for token, original in (mapa or {}).items() if original), key=lambda par: -len(par[0]))
        self.nuevos: dict[str, str] = {}

    def texto(self, valor: str) -> str:
        for original, token in self.inverso:
            valor = valor.replace(original, token)
        return valor

    def valor(self, valor: Any, ruta: str) -> Any:
        if isinstance(valor, dict):
            return {k: self.valor(v, f"{ruta}.{k}" if ruta else k) for k, v in valor.items()}
        if isinstance(valor, list):
            return [self.valor(v, f"{ruta}.*") for v in valor]
        if not isinstance(valor, str) or not valor.strip():
            return valor
        texto = self.texto(valor)
        tipo = IDENTIFICANTES.get(_ruta_normalizada(ruta))
        if tipo is None or _TOKEN.match(texto.strip()):
            return texto
        # Un dato identificante que no vino del documento (lo escribió la persona): token nuevo, sin el valor.
        return self.nuevos.setdefault(valor.strip(), f"[{tipo}_C{len(self.nuevos) + 1}]")


class ServicioReferencia:
    def __init__(self, session: Session):
        self.session = session

    def alimentar(self, doc: Documento, resultado: ResultadoTriaje, *, version_pack: str | None) -> list[CasoReferencia]:
        """Cada corrección del documento que todavía no esté en el conjunto entra una sola vez."""
        existentes = set(self.session.scalars(select(CasoReferencia.correccion_id).where(CasoReferencia.documento_id == doc.documento_id)))
        pendientes = [c for c in doc.correcciones if c.id is not None and c.id not in existentes]
        if not pendientes:
            return []
        seudonimo = Seudonimo(doc.mapa_reidentificacion)
        propuesta = seudonimo.valor(doc.propuesta_json, "") if doc.propuesta_json else None
        nivel_propuesto = ((doc.propuesta_json or {}).get("clasificacion") or {}).get("nivel_prioridad_propuesto")
        casos = []
        for c in pendientes:
            caso = CasoReferencia(
                correccion_id=c.id, documento_id=doc.documento_id, version=doc.version,
                origen="transcripcion" if c.extraido is None and c.campo != "nivel_prioridad" else "correccion",
                campo=c.campo, extraido=seudonimo.valor(c.extraido, c.campo), corregido=seudonimo.valor(c.corregido, c.campo),
                usuario=c.usuario, tipo_documento=resultado.clasificacion.tipo.value, canal_origen=doc.canal_origen, pais=doc.pais_origen,
                texto_seudonimizado=seudonimo.texto(doc.texto_seudonimizado or ""), propuesta_json=propuesta,
                nivel_propuesto=nivel_propuesto, nivel_antes=_nivel_antes(c, doc), nivel_resultante=resultado.clasificacion.nivel_prioridad.value,
                hallazgos_json=list(resultado.extraccion.hallazgos_criticos_detectados),
                modelo_llm=doc.modelo_llm, version_prompt=doc.version_prompt, version_reglas=resultado.version_reglas, version_pack=version_pack,
            )
            self.session.add(caso)
            casos.append(caso)
        self.session.flush()
        return casos

    def listar(self, *, limit: int = 200) -> list[CasoReferencia]:
        return list(self.session.scalars(select(CasoReferencia).order_by(CasoReferencia.id.desc()).limit(limit)))

    def todos(self) -> list[CasoReferencia]:
        return list(self.session.scalars(select(CasoReferencia).order_by(CasoReferencia.id)))

    def resumen(self) -> dict:
        casos = self.todos()
        por_campo = Counter(_ruta_normalizada(c.campo) for c in casos)
        por_tipo = Counter(c.tipo_documento or "sin tipo" for c in casos)
        # RN-R3: el LLM no propuso Crítico y una persona lo subió a Crítico.
        subidos_a_critico = sorted({c.documento_id for c in casos if c.campo == "nivel_prioridad" and c.corregido == "Crítico" and c.extraido != "Crítico"})
        return {
            "casos": len(casos), "documentos": len({c.documento_id for c in casos}),
            "por_campo": [{"campo": campo, "casos": n} for campo, n in por_campo.most_common()],
            "por_tipo": [{"tipo": tipo, "casos": n} for tipo, n in por_tipo.most_common()],
            "por_origen": dict(Counter(c.origen for c in casos)),
            "subidos_a_critico": subidos_a_critico,
        }


def _nivel_antes(c: Correccion, doc: Documento) -> str | None:
    if c.campo == "nivel_prioridad":
        return c.extraido if isinstance(c.extraido, str) else None
    return doc.nivel_prioridad


def caso_como_dict(c: CasoReferencia, *, completo: bool = False) -> dict:
    datos = {
        "id": c.id, "documento_id": c.documento_id, "version": c.version, "origen": c.origen, "campo": c.campo,
        "extraido": c.extraido, "corregido": c.corregido, "usuario": c.usuario, "tipo_documento": c.tipo_documento,
        "canal_origen": c.canal_origen, "pais": c.pais, "nivel_propuesto": c.nivel_propuesto, "nivel_antes": c.nivel_antes,
        "nivel_resultante": c.nivel_resultante, "hallazgos": c.hallazgos_json or [], "modelo_llm": c.modelo_llm,
        "version_prompt": c.version_prompt, "version_reglas": c.version_reglas, "version_pack": c.version_pack,
        "creado_en": c.creado_en.isoformat() if c.creado_en else None,
    }
    if completo:
        datos["texto_seudonimizado"] = c.texto_seudonimizado
        datos["propuesta"] = c.propuesta_json
    return datos
