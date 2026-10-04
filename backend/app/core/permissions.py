from sqlalchemy import select
from app.models.administration import RolePermission, EmployeeDenial

PERMISSIONS = {
    "DOCUMENTS_READ": "Consultar documentos y bandejas",
    "DOCUMENTS_UPLOAD": "Cargar documentos",
    "DOCUMENTS_PROCESS": "Ejecutar análisis",
    "DOCUMENTS_REVIEW": "Resolver revisión humana",
    "DOCUMENTS_DELETE": "Eliminar documentos",
    "PATIENTS_READ": "Consultar pacientes",
    "PATIENTS_EDIT": "Editar pacientes",
    "DESTINATIONS_READ": "Consultar destinos",
    "DESTINATIONS_MANAGE": "Administrar destinos y reglas",
}


def effective_permissions(account, session):
    if account.role == "SUPERADMIN":
        return sorted(PERMISSIONS), []
    grants = set(session.scalars(select(RolePermission.permission_code).where(
        RolePermission.role_id == account.assigned_role_id))) if account.assigned_role_id else set()
    denials = set(session.scalars(select(EmployeeDenial.permission_code).where(EmployeeDenial.account_id == account.id)))
    return sorted(grants - denials), sorted(denials)
