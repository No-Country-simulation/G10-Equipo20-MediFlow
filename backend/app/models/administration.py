from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Identity, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.document import Base


class ConfigurationVariable(Base):
    __tablename__ = "configuration_variables"
    __table_args__ = (CheckConstraint("name ~ '^[A-Z][A-Z0-9_]{0,99}$'", name="ck_configuration_name"),)
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Permission(Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(ForeignKey("permissions.code", ondelete="RESTRICT"), primary_key=True)


class EmployeeDenial(Base):
    __tablename__ = "employee_denials"
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(ForeignKey("permissions.code", ondelete="RESTRICT"), primary_key=True)
