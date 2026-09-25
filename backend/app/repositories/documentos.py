"""Capa de persistencia de documentos. No contiene reglas clínicas."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.documento import Documento, TransicionEstado
from app.schemas.resultado import EstadoDocumento
from app.services.ciclo_vida import validar_transicion


class RepositorioDocumentos:
    def __init__(self, session: Session):
        self.session = session

    def ultima_version(self, documento_id: str) -> Documento | None:
        consulta = (
            select(Documento)
            .where(Documento.documento_id == documento_id)
            .order_by(Documento.version.desc())
            .limit(1)
        )
        return self.session.scalars(consulta).first()

    def contar_versiones(self, documento_id: str) -> int:
        consulta = select(func.count()).select_from(Documento).where(Documento.documento_id == documento_id)
        return self.session.scalar(consulta) or 0

    def por_hash(self, hash_contenido: str, *, excluir_documento_id: str | None = None) -> Documento | None:
        consulta = select(Documento).where(Documento.hash_contenido == hash_contenido)
        if excluir_documento_id is not None:
            consulta = consulta.where(Documento.documento_id != excluir_documento_id)
        return self.session.scalars(consulta.order_by(Documento.id)).first()

    def crear_recibido(self, *, actor: str, motivo: str, **campos) -> Documento:
        """Crea el documento en RECIBIDO con su transición inicial (RN-I3, RN-P1)."""
        documento = Documento(estado=EstadoDocumento.RECIBIDO, **campos)
        documento.transiciones.append(
            TransicionEstado(de_estado=None, a_estado=EstadoDocumento.RECIBIDO, actor=actor, motivo=motivo)
        )
        self.session.add(documento)
        self.session.flush()
        return documento

    def transicionar(
        self, documento: Documento, nuevo_estado: EstadoDocumento, *, actor: str, motivo: str
    ) -> TransicionEstado:
        """Aplica una transición válida (RN-I1, RN-I2, RN-I5) y la registra (RN-I3)."""
        de = EstadoDocumento(documento.estado)
        validar_transicion(de, nuevo_estado, motivo=motivo)
        transicion = TransicionEstado(de_estado=de, a_estado=nuevo_estado, actor=actor, motivo=motivo)
        documento.transiciones.append(transicion)
        documento.estado = nuevo_estado
        self.session.flush()
        return transicion

    def guardar(self) -> None:
        self.session.commit()
