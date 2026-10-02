"""Límites de uso (RN-T1, RN-T2). No son dinero: son topes de llamadas y de documentos por tiempo.

RN-T1: hay un máximo de llamadas al LLM por periodo. Agotado, se detiene la extracción no crítica;
la detección determinística de críticos nunca se detiene, y un crítico detectado en el texto sí se extrae.
RN-T2: hay un máximo de documentos por minuto en la ingesta.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.repositories.documentos import RepositorioDocumentos


@dataclass(frozen=True)
class LimiteLLM:
    llamadas: int  # 0 = sin límite
    periodo_h: float = 24.0

    def agotado(self, repo: RepositorioDocumentos, ahora: datetime | None = None) -> bool:
        if self.llamadas <= 0:
            return False
        desde = (ahora or datetime.now(timezone.utc)) - timedelta(hours=self.periodo_h)
        return repo.lecturas_llm_desde(desde) >= self.llamadas

    def descripcion(self) -> str:
        return f"{self.llamadas} llamadas al LLM por {self.periodo_h:g} h"


@dataclass(frozen=True)
class LimiteIngesta:
    documentos_por_minuto: int  # 0 = sin límite

    def excedido(self, repo: RepositorioDocumentos, ahora: datetime | None = None) -> bool:
        if self.documentos_por_minuto <= 0:
            return False
        desde = (ahora or datetime.now(timezone.utc)) - timedelta(minutes=1)
        return repo.recibidos_desde(desde) >= self.documentos_por_minuto
