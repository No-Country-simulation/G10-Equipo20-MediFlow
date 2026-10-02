"""Lo que la API deja listo al arrancar: roles de la tabla K y, si la instalación lo pide, cuentas de demostración."""
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.semillas import sembrar_cuentas_demo, sembrar_roles


def preparar_instalacion(session: Session) -> dict[str, int]:
    settings = get_settings()
    roles = sembrar_roles(session)
    cuentas = sembrar_cuentas_demo(session, clave=settings.cuentas_demo_clave) if settings.cuentas_demo else 0
    return {"roles": roles, "cuentas": len(cuentas) if isinstance(cuentas, list) else cuentas}
