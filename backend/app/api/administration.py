"""Superadministrator configuration and staff access management."""
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import delete, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import password_hash, require_superadmin, same_origin
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.permissions import PERMISSIONS
from app.models.account import Account
from app.models.administration import ConfigurationVariable, EmployeeDenial, Permission, Role, RolePermission
from app.services.patients import validate_identity
from app.services.runtime_configuration import RESERVED, is_secret, seed_configuration

router = APIRouter(prefix="/admin", tags=["administration"],
                   dependencies=[Depends(require_superadmin), Depends(same_origin)])
Db = Annotated[Session, Depends(get_session)]


def commit(session):
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "DUPLICATE_OR_REFERENCED_RECORD") from None


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VariableInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(max_length=16384)


@router.get("/configuration")
def configuration(session: Db, settings: Annotated[Settings, Depends(get_settings)], response: Response):
    seed_configuration(session, settings)
    commit(session)
    response.headers["Cache-Control"] = "no-store"
    return [{"name": v.name, "value": None if is_secret(v.name) else v.value,
             "secret": is_secret(v.name), "configured": bool(v.value)}
            for v in session.scalars(select(ConfigurationVariable).order_by(ConfigurationVariable.name))]


@router.put("/configuration/{name}", status_code=204)
def save_variable(name: str, payload: VariableInput, session: Db):
    import re
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", name):
        raise HTTPException(422, "UPPERCASE_NAME_REQUIRED")
    value = payload.value.strip()
    if name == "USAR_GEMINI" and value not in ("true", "false"):
        raise HTTPException(422, "BOOLEAN_VALUE_REQUIRED")
    if name in ("GEMINI_MODEL", "OPENAI_MODEL") and not value:
        raise HTTPException(422, "MODEL_REQUIRED")
    variable = session.get(ConfigurationVariable, name)
    if variable is None:
        session.add(ConfigurationVariable(name=name, value=value))
    else:
        variable.value = value
    commit(session)
    return Response(status_code=204)


@router.delete("/configuration/{name}", status_code=204)
def remove_variable(name: str, session: Db):
    if name in RESERVED:
        raise HTTPException(409, "RESERVED_VARIABLE")
    variable = session.get(ConfigurationVariable, name)
    if variable is None:
        raise HTTPException(404, "VARIABLE_NOT_FOUND")
    session.delete(variable)
    commit(session)
    return Response(status_code=204)


class PermissionInput(Input):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,99}$")
    name: str = Field(min_length=2, max_length=150)


@router.get("/permissions")
def permissions(session: Db):
    return [{"code": p.code, "name": p.name, "builtin": p.code in PERMISSIONS}
            for p in session.scalars(select(Permission).order_by(Permission.code))]


@router.post("/permissions", status_code=201)
def create_permission(payload: PermissionInput, session: Db):
    session.add(Permission(**payload.model_dump()))
    commit(session)
    return payload


@router.delete("/permissions/{code}", status_code=204)
def remove_permission(code: str, session: Db):
    if code in PERMISSIONS:
        raise HTTPException(409, "BUILTIN_PERMISSION")
    record = session.get(Permission, code)
    if record is None:
        raise HTTPException(404, "PERMISSION_NOT_FOUND")
    session.delete(record)
    commit(session)
    return Response(status_code=204)


class RoleInput(Input):
    name: str = Field(min_length=2, max_length=100)
    permissions: list[str] = Field(max_length=200)


def check_permissions(codes, session):
    known = set(session.scalars(select(Permission.code).where(Permission.code.in_(codes))))
    if set(codes) != known:
        raise HTTPException(422, "UNKNOWN_PERMISSION")


def role_output(role, session):
    return {"id": role.id, "name": role.name,
            "permissions": sorted(session.scalars(select(RolePermission.permission_code).where(RolePermission.role_id == role.id)))}


@router.get("/roles")
def roles(session: Db):
    return [role_output(r, session) for r in session.scalars(select(Role).order_by(Role.name))]


@router.post("/roles", status_code=201)
def create_role(payload: RoleInput, session: Db):
    check_permissions(payload.permissions, session)
    role = Role(name=payload.name)
    session.add(role)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "ROLE_ALREADY_EXISTS") from None
    session.add_all([RolePermission(role_id=role.id, permission_code=p) for p in set(payload.permissions)])
    commit(session)
    return role_output(role, session)


@router.put("/roles/{role_id}")
def update_role(role_id: int, payload: RoleInput, session: Db):
    role = session.get(Role, role_id)
    if role is None:
        raise HTTPException(404, "ROLE_NOT_FOUND")
    check_permissions(payload.permissions, session)
    role.name = payload.name
    session.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
    session.add_all([RolePermission(role_id=role.id, permission_code=p) for p in set(payload.permissions)])
    commit(session)
    return role_output(role, session)


@router.delete("/roles/{role_id}", status_code=204)
def remove_role(role_id: int, session: Db):
    role = session.get(Role, role_id)
    if role is None:
        raise HTTPException(404, "ROLE_NOT_FOUND")
    if session.scalar(select(func.count()).select_from(Account).where(Account.assigned_role_id == role_id)):
        raise HTTPException(409, "ROLE_IN_USE")
    session.delete(role)
    commit(session)
    return Response(status_code=204)


class EmployeeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=255)
    country: str
    identity_number: str = Field(min_length=1, max_length=40)
    contact: str = Field(max_length=100)
    email: EmailStr
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role_id: int
    denied_permissions: list[str] = Field(default_factory=list, max_length=200)
    active: bool = True


def employee_output(account, session):
    return {"id": account.id, "name": account.name, "country": account.country,
            "identity_number": account.identity_number, "contact": account.contact, "email": account.email,
            "role_id": account.assigned_role_id, "role_name": session.get(Role, account.assigned_role_id).name,
            "active": account.active, "denied_permissions": sorted(session.scalars(
                select(EmployeeDenial.permission_code).where(EmployeeDenial.account_id == account.id)))}


def write_employee(account, payload, session):
    identity = validate_identity(payload.country, payload.identity_number)
    if identity is None:
        raise HTTPException(422, "PATIENT_IDENTITY_INVALID_FORMAT")
    if session.get(Role, payload.role_id) is None:
        raise HTTPException(422, "ROLE_NOT_FOUND")
    check_permissions(payload.denied_permissions, session)
    if account.id is None and not payload.password:
        raise HTTPException(422, "PASSWORD_REQUIRED")
    account.name = payload.name.strip()
    if len(account.name) < 2:
        raise HTTPException(422, "NAME_REQUIRED")
    account.country, account.identity_type, account.identity_number = payload.country, *identity
    account.contact, account.email = payload.contact.strip(), str(payload.email).lower()
    account.assigned_role_id, account.active = payload.role_id, payload.active
    if payload.password:
        account.password_hash = password_hash(payload.password)
    session.add(account)
    try:
        session.flush()
        session.execute(delete(EmployeeDenial).where(EmployeeDenial.account_id == account.id))
        session.add_all([EmployeeDenial(account_id=account.id, permission_code=p) for p in set(payload.denied_permissions)])
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "ACCOUNT_ALREADY_EXISTS") from None
    return employee_output(account, session)


@router.get("/employees")
def employees(session: Db):
    return [employee_output(a, session) for a in session.scalars(select(Account).where(Account.role == "EMPLOYEE").order_by(Account.name))]


@router.post("/employees", status_code=201)
def create_employee(payload: EmployeeInput, session: Db):
    return write_employee(Account(role="EMPLOYEE", created_at=datetime.now(UTC)), payload, session)


@router.put("/employees/{account_id}")
def update_employee(account_id: int, payload: EmployeeInput, session: Db):
    account = session.get(Account, account_id)
    if account is None or account.role != "EMPLOYEE":
        raise HTTPException(404, "EMPLOYEE_NOT_FOUND")
    return write_employee(account, payload, session)
