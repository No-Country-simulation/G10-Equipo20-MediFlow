"""Siembra de la instalación: los roles de la tabla K. Las cuentas las crea la propia instalación: la primera
desde la pantalla de ingreso (RN-S3) y las demás el administrador (RN-K5)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gobierno import Rol
from app.services.roles_base import ROLES_BASE


def sembrar_roles(session: Session) -> int:
    """Repone los roles que falten en la tabla. Devuelve cuántos creó. No pisa los existentes."""
    existentes = set(session.scalars(select(Rol.id)).all())
    nuevos = 0
    for datos in ROLES_BASE:
        if datos["id"] in existentes:
            continue
        session.add(Rol(**datos))
        nuevos += 1
    if nuevos:
        session.commit()
    return nuevos
