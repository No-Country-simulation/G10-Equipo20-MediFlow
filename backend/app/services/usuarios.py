"""Usuarios, roles y accesos (dominio K).

En el modo de demostración (sin EXIGIR_SESION), quien no está registrado firma con su nombre.
Quien sí está registrado queda sujeto a su rol (RN-K1, RN-K2), a su estado (RN-K4) y a su tipo (RN-K5).
RN-K3: cada acceso a un documento se registra con quién, cuándo y qué vio.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gobierno import AccesoDocumento, Usuario
from app.services.errores import ErrorDeRevision

ROLES = ("auditor_clinico", "quimico_farmaceutico", "auditor_autorizaciones", "jefe_urgencias", "gestor", "administrador")
TIPOS = ("persona", "servicio")

# Qué rol ejecuta cada acción (tabla K). Quien configura no revisa; quien administra no ve datos clínicos (RN-K2).
ACCIONES: dict[str, set[str]] = {
    "resolver_revision": {"auditor_clinico", "jefe_urgencias"},
    "acusar_alerta": {"jefe_urgencias", "auditor_clinico"},
    "verificar_receta": {"quimico_farmaceutico"},
    "resolver_autorizacion": {"auditor_autorizaciones"},
    "editar_paciente": {"auditor_clinico"},
    "configurar": {"gestor"},
    "administrar": {"administrador"},
}
ACCIONES_CLINICAS = {"resolver_revision", "acusar_alerta", "verificar_receta", "resolver_autorizacion", "editar_paciente"}


class ServicioUsuarios:
    def __init__(self, session: Session):
        self.session = session

    def buscar(self, usuario: str) -> Usuario | None:
        return self.session.scalars(select(Usuario).where(Usuario.usuario == usuario.strip())).first()

    def listar(self) -> list[Usuario]:
        return list(self.session.scalars(select(Usuario).order_by(Usuario.id)))

    def crear(self, *, usuario: str, nombre: str, rol: str, tipo: str, actor: str) -> Usuario:
        if rol not in ROLES:
            raise ErrorDeRevision(422, f"rol desconocido: {rol}. Roles: {', '.join(ROLES)}")
        if tipo not in TIPOS:
            raise ErrorDeRevision(422, f"tipo desconocido: {tipo}. Tipos: {', '.join(TIPOS)}")
        if self.buscar(usuario) is not None:
            raise ErrorDeRevision(409, f"el usuario {usuario} ya existe")
        u = Usuario(usuario=usuario.strip(), nombre=nombre.strip(), rol=rol, tipo=tipo, creado_por=actor.strip())
        self.session.add(u)
        self.session.commit()
        self.session.refresh(u)
        return u

    def cambiar_estado(self, usuario: str, *, activo: bool) -> Usuario:
        u = self.buscar(usuario)
        if u is None:
            raise ErrorDeRevision(404, "usuario no encontrado")
        u.activo = activo
        u.desactivado_en = None if activo else datetime.now(timezone.utc)  # RN-K4: efecto inmediato
        self.session.commit()
        self.session.refresh(u)
        return u

    def activos_con_rol(self, rol: str) -> int:
        return sum(1 for u in self.listar() if u.activo and u.rol == rol and u.tipo == "persona")

    # --- validación del actor -------------------------------------------------------------------

    def validar_actor(self, usuario: str, accion: str, rol_declarado: str | None = None) -> None:
        """Lanza 403 cuando un usuario registrado no puede ejecutar la acción. Un desconocido pasa (MVP)."""
        u = self.buscar(usuario)
        if u is None:
            return
        if not u.activo:
            raise ErrorDeRevision(403, f"RN-K4: {u.usuario} está desactivado y perdió el acceso")
        if u.tipo == "servicio" and accion in ACCIONES_CLINICAS:
            raise ErrorDeRevision(403, "RN-K5: ninguna acción clínica la ejecuta una cuenta de servicio")
        if rol_declarado and rol_declarado != u.rol:
            raise ErrorDeRevision(403, f"RN-K1: {u.usuario} está registrado como {u.rol}, no como {rol_declarado}")
        permitidos = ACCIONES.get(accion, set())
        if u.rol not in permitidos:
            raise ErrorDeRevision(403, f"RN-K2: el rol {u.rol} no ejecuta {accion}. Quien configura no revisa; quien administra no ve datos clínicos")

    # --- accesos (RN-K3) --------------------------------------------------------------------------

    def registrar_acceso(self, documento_id: str, usuario: str | None, accion: str) -> None:
        if not usuario or not usuario.strip():
            return
        self.session.add(AccesoDocumento(documento_id=documento_id, usuario=usuario.strip(), accion=accion))
        self.session.commit()

    def accesos(self, documento_id: str | None = None, limit: int = 200) -> list[AccesoDocumento]:
        consulta = select(AccesoDocumento).order_by(AccesoDocumento.id.desc()).limit(limit)
        if documento_id:
            consulta = consulta.where(AccesoDocumento.documento_id == documento_id)
        return list(self.session.scalars(consulta))
