"""Lo que la API deja listo al arrancar: roles de la tabla K y el tipo de los documentos anteriores a la columna `tipo` (RN-J9)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documento import Documento
from app.services.semillas import sembrar_roles


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
    return {"roles": sembrar_roles(session), "tipos_completados": completar_tipos(session)}
