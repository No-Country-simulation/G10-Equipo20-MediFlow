"""Primera cuenta de administrador de una instalación con inicio de sesión obligatorio.

Uso, después de aplicar las migraciones:
    ADMIN_CLAVE_INICIAL=una-clave-larga python -m scripts.crear_administrador

El usuario sale de ADMIN_USUARIO (por defecto, admin). Si la cuenta ya existe no se toca:
una clave olvidada la cambia otro administrador desde Administración.
"""
import sys

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_engine
from app.core.sesiones import hash_clave
from app.services.errores import ErrorDeRevision
from app.services.usuarios import ServicioUsuarios, validar_clave


def crear_administrador(session: Session, usuario: str, clave: str) -> str:
    """Devuelve "creada" o "ya_existe". Falla si la clave es corta o el usuario ya existe con otro rol."""
    try:
        validar_clave(clave, usuario)
    except ErrorDeRevision as error:
        raise ValueError(f"ADMIN_CLAVE_INICIAL: {error.detalle}") from error
    servicio = ServicioUsuarios(session)
    existente = servicio.buscar(usuario)
    if existente is not None:
        if existente.rol != "administrador":
            raise ValueError(f"el usuario {usuario} ya existe con el rol {existente.rol}")
        return "ya_existe"
    cuenta = servicio.crear(usuario=usuario, nombre="Administrador del sistema", rol="administrador", tipo="persona", actor="instalacion")
    cuenta.clave_hash = hash_clave(clave)
    session.commit()
    return "creada"


def main() -> int:
    settings = get_settings()
    try:
        with Session(get_engine()) as session:
            resultado = crear_administrador(session, settings.admin_usuario, settings.admin_clave_inicial)
    except ValueError as error:
        print(f"No se creó la cuenta: {error}", file=sys.stderr)
        return 1
    print(f"Cuenta {settings.admin_usuario}: {resultado}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
