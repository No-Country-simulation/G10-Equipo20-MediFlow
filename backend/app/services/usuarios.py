"""Usuarios, roles y accesos (dominio K).

En el modo de demostración (sin EXIGIR_SESION), quien no está registrado firma con su nombre.
Quien sí está registrado queda sujeto a su rol (RN-K1, RN-K2), a su estado (RN-K4) y a su tipo (RN-K5).
RN-K3: cada acceso a un documento se registra con quién, cuándo y qué vio.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.gobierno import AccesoDocumento, EventoSesion, Rol, Usuario
from app.services.errores import ErrorDeRevision
from app.services.roles_base import ROLES_BASE

# Los roles y sus acciones viven en la tabla `roles` (tabla K). Estas constantes solo repiten la base para
# quien necesite la lista sin sesión abierta (por ejemplo, el script del primer administrador).
ROLES = tuple(r["id"] for r in ROLES_BASE)
TIPOS = ("persona", "servicio")
ACCIONES_CLINICAS = {"resolver_revision", "acusar_alerta", "verificar_receta", "resolver_autorizacion", "editar_paciente"}


def validar_clave(clave: str, usuario: str = "") -> None:
    """Política mínima de claves: largo configurable, letras y números o símbolos, y distinta del usuario."""
    minima = get_settings().clave_minima
    if len(clave) < minima:
        raise ErrorDeRevision(422, f"la clave necesita al menos {minima} caracteres")
    if not any(c.isdigit() for c in clave) or not any(c.isalpha() for c in clave):
        raise ErrorDeRevision(422, "la clave debe combinar letras y números")
    if usuario and clave.strip().lower() == usuario.strip().lower():
        raise ErrorDeRevision(422, "la clave no puede ser el nombre de usuario")


class ServicioUsuarios:
    def __init__(self, session: Session):
        self.session = session

    def hay_cuentas(self) -> bool:
        return self.session.scalars(select(Usuario.id).limit(1)).first() is not None

    # --- eventos de sesión (RN-K3, RN-G4) ---------------------------------------------------------

    def registrar_evento(self, usuario: str, evento: str, detalle: str = "") -> None:
        self.session.add(EventoSesion(usuario=usuario, evento=evento, detalle=detalle[:256]))

    def eventos_sesion(self, limit: int = 200) -> list[EventoSesion]:
        return list(self.session.scalars(select(EventoSesion).order_by(EventoSesion.id.desc()).limit(limit)))

    def buscar(self, usuario: str) -> Usuario | None:
        return self.session.scalars(select(Usuario).where(Usuario.usuario == usuario.strip())).first()

    # --- roles (tabla K como datos) --------------------------------------------------------------

    def roles(self) -> list[Rol]:
        """Los roles de la tabla. Si la tabla está vacía (base recién creada sin migración), se repone desde la base."""
        roles = list(self.session.scalars(select(Rol).order_by(Rol.orden)))
        if not roles:
            from app.services.semillas import sembrar_roles  # noqa: PLC0415 - evita import circular

            sembrar_roles(self.session)
            roles = list(self.session.scalars(select(Rol).order_by(Rol.orden)))
        return roles

    def rol(self, id_rol: str) -> Rol | None:
        return next((r for r in self.roles() if r.id == id_rol), None)

    def roles_de_accion(self, accion: str) -> set[str]:
        """Qué roles ejecutan una acción (tabla K). Quien configura no revisa; quien administra no ve datos clínicos (RN-K2)."""
        return {r.id for r in self.roles() if accion in r.acciones}

    def listar(self) -> list[Usuario]:
        return list(self.session.scalars(select(Usuario).order_by(Usuario.id)))

    def crear(self, *, usuario: str, nombre: str, rol: str, tipo: str, actor: str) -> Usuario:
        ids = [r.id for r in self.roles()]
        if rol not in ids:
            raise ErrorDeRevision(422, f"rol desconocido: {rol}. Roles: {', '.join(ids)}")
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
        permitidos = self.roles_de_accion(accion)
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
