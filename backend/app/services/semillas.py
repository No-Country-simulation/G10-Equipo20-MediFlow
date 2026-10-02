"""Siembra de la instalación: roles de la tabla K y, si la instalación lo pide, cuentas de demostración.

Las cuentas de demostración existen para el hackathon: una persona por rol, con clave, creadas por el backend
con todos sus atributos. En producción se desactivan desde Administración (RN-K4) y CUENTAS_DEMO va en false.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.sesiones import hash_clave
from app.models.gobierno import Rol, Usuario
from app.services.roles_base import ROLES_BASE

# (usuario, rol). Los nombres son ficticios; la clave la define CUENTAS_DEMO_CLAVE.
CUENTAS_DEMO: list[tuple[str, str]] = [
    ("admin", "administrador"),
    ("aud.ana", "auditor_clinico"),
    ("qf.maria", "quimico_farmaceutico"),
    ("aut.luis", "auditor_autorizaciones"),
    ("jefe.rojas", "jefe_urgencias"),
    ("gestor.paz", "gestor"),
]
NOMBRES_DEMO = {
    "admin": "Administrador del sistema",
    "aud.ana": "Ana Torres",
    "qf.maria": "María Camargo",
    "aut.luis": "Luis Herrera",
    "jefe.rojas": "Andrés Rojas",
    "gestor.paz": "Paz Velásquez",
}


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


def sembrar_cuentas_demo(session: Session, *, clave: str) -> list[str]:
    """Crea las cuentas de demostración que falten, con clave. Devuelve los usuarios creados."""
    existentes = set(session.scalars(select(Usuario.usuario)).all())
    creados: list[str] = []
    for usuario, rol in CUENTAS_DEMO:
        if usuario in existentes:
            continue
        session.add(Usuario(usuario=usuario, nombre=NOMBRES_DEMO[usuario], rol=rol, tipo="persona",
                            creado_por="instalacion", clave_hash=hash_clave(clave)))
        creados.append(usuario)
    if creados:
        session.commit()
    return creados
