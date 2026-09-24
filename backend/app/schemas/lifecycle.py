from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class DocumentStatus(StrEnum):
    RECIBIDO = "RECIBIDO"
    VALIDADO = "VALIDADO"
    CLASIFICADO = "CLASIFICADO"
    EXTRAIDO = "EXTRAIDO"
    EVALUADO = "EVALUADO"
    ENRUTADO = "ENRUTADO"
    ENTREGADO = "ENTREGADO"
    RECHAZADO = "RECHAZADO"
    FALLO_TECNICO = "FALLO_TECNICO"
    EN_REVISION_HUMANA = "EN_REVISION_HUMANA"
    RESUELTO = "RESUELTO"


class StateEvent(BaseModel):
    status: DocumentStatus
    occurred_at: datetime
    reason: str
    attempt: int = 0
