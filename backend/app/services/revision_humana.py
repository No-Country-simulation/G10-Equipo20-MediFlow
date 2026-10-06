"""Quién tiene cada caso de la cola de revisión (RN-J2, RN-J3).

Reasignar y escalar no deciden nada sobre el documento: sigue EN_REVISION_HUMANA y el grafo sigue esperando a la
persona (RN-I4). Solo cambia a quién le toca, y eso queda en el historial de decisiones (RN-G2).
"""
from datetime import datetime, timezone

from app.models.documento import Documento
from app.models.gobierno import Usuario
from app.packs.modelos import ColaRevision
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.resultado import DecisionRegistrada, ResultadoTriaje
from app.services.errores import ErrorDeRevision
from app.services.usuarios import ServicioUsuarios

ACCION = "resolver_revision"
# RN-J2: el siguiente rol de la cola de revisión. El auditor clínico resuelve; el jefe de urgencias recibe lo que
# el auditor escala o deja vencer. Por encima no hay otro rol de la tabla K.
ROL_ESCALAMIENTO = "jefe_urgencias"


def plazo_minutos(nivel: str | None, cola: ColaRevision) -> int:
    """RN-J2: Crítico 15 min, Urgente 2 h, Rutina 24 h hábiles."""
    if nivel == "Crítico":
        return cola.critico_min
    if nivel == "Urgente":
        return cola.urgente_h * 60
    return cola.rutina_h_habiles * 60


def _utc(momento: datetime) -> datetime:
    return momento if momento.tzinfo is not None else momento.replace(tzinfo=timezone.utc)


class ServicioRevision:
    def __init__(self, repositorio: RepositorioDocumentos):
        self.repo = repositorio
        self.usuarios = ServicioUsuarios(repositorio.session)

    def revisores(self) -> list[Usuario]:
        """A quién se puede reasignar un caso: personas activas cuyo rol resuelve la revisión (RN-K2, RN-K4, RN-K5)."""
        roles = self.usuarios.roles_de_accion(ACCION)
        return [u for u in self.usuarios.listar() if u.activo and u.tipo == "persona" and u.rol in roles]

    def reasignar(self, doc: Documento, *, usuario: str, rol: str, a_usuario: str, motivo: str) -> ResultadoTriaje:
        """RN-J3: el caso pasa a nombre de otro revisor (o de uno mismo, para tomarlo). Si estaba escalado a un rol
        y quien lo toma es de otro rol, el escalamiento queda resuelto."""
        self._en_revision(doc)
        destino = self.usuarios.buscar(a_usuario or "")
        if destino is None:
            raise ErrorDeRevision(422, "RN-J3: reasignar exige la cuenta de un revisor existente")
        if not destino.activo:
            raise ErrorDeRevision(422, f"RN-K4: {destino.usuario} está desactivado y no puede recibir casos")
        if destino.tipo != "persona":
            raise ErrorDeRevision(422, "RN-K5: una cuenta de servicio no revisa documentos")
        if destino.rol not in self.usuarios.roles_de_accion(ACCION):
            raise ErrorDeRevision(422, f"RN-K2: el rol {destino.rol} no resuelve la revisión humana")
        doc.asignado_a = destino.usuario
        if doc.escalado_a_rol and destino.rol != doc.escalado_a_rol:
            doc.escalado_a_rol = None
        return self._registrar(doc, regla="RN-J3", evidencia=f"{usuario} ({rol}): {motivo.strip() or 'sin motivo'}",
                               decision=f"reasignado a {destino.usuario}")

    def escalar(self, doc: Documento, *, usuario: str, rol: str, motivo: str) -> ResultadoTriaje:
        """RN-J3: el caso sube al siguiente rol de la cola, con motivo. Una sola vez: por encima no hay otro rol."""
        self._en_revision(doc)
        if not motivo.strip():
            raise ErrorDeRevision(422, "RN-J3: escalar exige motivo")
        if rol == ROL_ESCALAMIENTO:
            raise ErrorDeRevision(409, f"RN-J3: no hay rol por encima de {ROL_ESCALAMIENTO} en la cola de revisión")
        if doc.escalado_a_rol == ROL_ESCALAMIENTO:
            raise ErrorDeRevision(409, f"RN-J3: el caso ya está escalado a {ROL_ESCALAMIENTO}")
        doc.escalado_a_rol = ROL_ESCALAMIENTO
        doc.asignado_a = None
        return self._registrar(doc, regla="RN-J3", evidencia=f"{usuario} ({rol}): {motivo.strip()}",
                               decision=f"escalado a {ROL_ESCALAMIENTO}")

    def escalar_vencidas(self, cola: ColaRevision, ahora: datetime | None = None) -> list[Documento]:
        """RN-J2: vencido el plazo de atención en cola, el caso escala solo al siguiente rol. Una sola vez, y queda
        en el historial con quién lo tenía."""
        ahora = _utc(ahora or datetime.now(timezone.utc))  # SQLite devuelve fechas sin zona
        escalados: list[Documento] = []
        for doc in self.repo.en_revision():
            if doc.escalado_a_rol:
                continue
            plazo = plazo_minutos(doc.nivel_prioridad, cola)
            en_cola = int((ahora - _utc(doc.creado_en)).total_seconds() // 60)
            if en_cola < plazo:
                continue
            quien = f", lo tenía {doc.asignado_a}" if doc.asignado_a else ""
            doc.escalado_a_rol = ROL_ESCALAMIENTO
            doc.asignado_a = None
            self._registrar(doc, regla="RN-J2", evidencia=f"{en_cola} min en cola, plazo {plazo} min{quien}",
                            decision=f"escalado a {ROL_ESCALAMIENTO}", guardar=False)
            escalados.append(doc)
        if escalados:
            self.repo.guardar()
        return escalados

    @staticmethod
    def _en_revision(doc: Documento) -> None:
        if doc.estado != "EN_REVISION_HUMANA":
            raise ErrorDeRevision(409, f"RN-I4: el documento está en {doc.estado}, no en revisión humana")

    def _registrar(self, doc: Documento, *, regla: str, evidencia: str, decision: str, guardar: bool = True) -> ResultadoTriaje:
        resultado = ResultadoTriaje.model_validate(doc.resultado_json)
        resultado.historial_decisiones.append(DecisionRegistrada(regla=regla, evidencia=evidencia, decision=decision))
        doc.resultado_json = resultado.model_dump(mode="json")
        if guardar:
            self.repo.guardar()
        return resultado
