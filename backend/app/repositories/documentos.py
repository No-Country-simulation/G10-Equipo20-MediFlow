"""Capa de persistencia de documentos. No contiene reglas clínicas."""
from datetime import datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.alerta import Alerta, Correccion
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

    def listar(self, *, estado: str | None = None, nivel: str | None = None, q: str = "", limit: int = 20, offset: int = 0,
               tipos: list[str] | None = None) -> tuple[list[Documento], int]:
        """Última versión de cada documento, más reciente primero, con filtros y paginación. `tipos` acota lo que ve un rol (RN-J9)."""
        ultima = (
            select(Documento.documento_id, func.max(Documento.version).label("version"))
            .group_by(Documento.documento_id)
            .subquery()
        )
        consulta = select(Documento).join(ultima, (Documento.documento_id == ultima.c.documento_id) & (Documento.version == ultima.c.version))
        if estado:
            consulta = consulta.where(Documento.estado == estado)
        if nivel:
            consulta = consulta.where(Documento.nivel_prioridad == nivel)
        if tipos is not None:
            consulta = consulta.where(Documento.tipo.in_(tipos))
        if q.strip():
            patron = f"%{q.strip()}%"
            consulta = consulta.where(Documento.documento_id.ilike(patron) | Documento.nombre_archivo.ilike(patron))
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        filas = self.session.scalars(consulta.order_by(Documento.creado_en.desc(), Documento.id.desc()).limit(limit).offset(offset))
        return list(filas), total

    def ultimas_versiones(self, *, estado: str | None = None) -> list[Documento]:
        documentos, _ = self.listar(estado=estado, limit=5000)
        return documentos

    def entregados_desde(self, desde: datetime) -> int:
        consulta = (
            select(func.count(func.distinct(TransicionEstado.documento_pk)))
            .where(TransicionEstado.a_estado == EstadoDocumento.ENTREGADO, TransicionEstado.fecha_hora >= desde)
        )
        return self.session.scalar(consulta) or 0

    def lecturas_llm_desde(self, desde: datetime) -> int:
        """RN-T1: documentos leídos por el LLM en el periodo (cada lectura es una llamada que produjo propuesta)."""
        consulta = select(func.count(Documento.id)).where(Documento.modelo_llm.is_not(None), Documento.creado_en >= desde)
        return self.session.scalar(consulta) or 0

    def recibidos_desde(self, desde: datetime) -> int:
        """RN-T2: documentos recibidos en la ventana."""
        return self.session.scalar(select(func.count(Documento.id)).where(Documento.creado_en >= desde)) or 0

    def version_previa(self, documento: Documento) -> Documento | None:
        """RN-O2: la versión anterior del mismo documento_id."""
        consulta = (
            select(Documento)
            .where(Documento.documento_id == documento.documento_id, Documento.version < documento.version)
            .order_by(Documento.version.desc())
            .limit(1)
        )
        return self.session.scalars(consulta).first()

    # --- alertas (RN-F1, RN-Q1, RN-Q5) -----------------------------------------------

    def alerta_activa(self, documento: Documento) -> Alerta | None:
        return next((a for a in documento.alertas if a.nivel == "Crítico"), None)

    def contar_alertas(self, documento_id: str) -> int:
        consulta = select(func.count()).select_from(Alerta).where(Alerta.documento_id == documento_id)
        return self.session.scalar(consulta) or 0

    def listar_alertas(self, *, estado_acuse: str | None = None, limit: int = 100) -> list[Alerta]:
        """Pendientes primero y, dentro de cada grupo, la más antigua primero (RN-J1)."""
        orden = case((Alerta.estado_acuse == "pendiente", 0), (Alerta.estado_acuse == "escalado", 1), else_=2)
        consulta = select(Alerta)
        if estado_acuse:
            consulta = consulta.where(Alerta.estado_acuse == estado_acuse)
        consulta = consulta.order_by(orden, Alerta.emitida_en, Alerta.id).limit(limit)
        return list(self.session.scalars(consulta))

    def alerta_por_documento_id(self, documento_id: str) -> Alerta | None:
        consulta = select(Alerta).where(Alerta.documento_id == documento_id).order_by(Alerta.id.desc()).limit(1)
        return self.session.scalars(consulta).first()

    def crear_alerta(self, documento: Documento, *, nivel: str, canal: str, destinatario: str, mensaje: str, enlace: str | None) -> Alerta:
        alerta = Alerta(documento_id=documento.documento_id, nivel=nivel, canal=canal, destinatario=destinatario, mensaje=mensaje, enlace=enlace)
        documento.alertas.append(alerta)
        self.session.flush()
        return alerta

    def acusar_alerta(self, alerta: Alerta, usuario: str) -> Alerta:
        alerta.estado_acuse = "acusado"
        alerta.acusado_por = usuario
        alerta.acusado_en = datetime.now(timezone.utc)
        self.session.flush()
        return alerta

    # --- revisión humana (RN-J1, RN-J8) -----------------------------------------------

    def en_revision(self) -> list[Documento]:
        """RN-J1: por prioridad clínica y luego por antigüedad, nunca por orden de llegada puro."""
        orden_prioridad = case(
            (Documento.nivel_prioridad == "Crítico", 0),
            (Documento.nivel_prioridad == "Urgente", 1),
            else_=2,
        )
        consulta = (
            select(Documento)
            .where(Documento.estado == EstadoDocumento.EN_REVISION_HUMANA)
            .order_by(orden_prioridad, Documento.creado_en, Documento.id)
        )
        return list(self.session.scalars(consulta))

    def registrar_correccion(self, documento: Documento, *, campo: str, extraido, corregido, usuario: str) -> Correccion:
        correccion = Correccion(campo=campo, extraido=extraido, corregido=corregido, usuario=usuario)
        documento.correcciones.append(correccion)
        self.session.flush()
        return correccion

    def guardar(self) -> None:
        self.session.commit()
