"""Lo que la API deja listo al arrancar: roles de la tabla K, cuentas de demostración si la instalación lo pide
y el tipo de los documentos anteriores a la columna `tipo` (RN-J9)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.documento import Documento
from app.services.semillas import sembrar_cuentas_demo, sembrar_roles


def completar_tipos(session: Session) -> int:
    """Documentos procesados antes de que el tipo viviera en su fila: se toma del resultado guardado."""
    completados = 0
    for doc in session.scalars(select(Documento).where(Documento.tipo.is_(None), Documento.resultado_json.is_not(None))):
        tipo = (doc.resultado_json or {}).get("clasificacion", {}).get("tipo")
        if tipo:
            doc.tipo = tipo
            completados += 1
    if completados:
        session.commit()
    return completados


def preparar_instalacion(session: Session) -> dict[str, int]:
    settings = get_settings()
    roles = sembrar_roles(session)
    cuentas = sembrar_cuentas_demo(session, clave=settings.cuentas_demo_clave) if settings.cuentas_demo else []
    return {"roles": roles, "cuentas": len(cuentas), "tipos_completados": completar_tipos(session)}
