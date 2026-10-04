"""Local configuration, roles and employee permissions."""
from alembic import op
import sqlalchemy as sa

revision = "0010_administration"
down_revision = "0009_document_contracts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("configuration_variables", sa.Column("name", sa.String(100), primary_key=True),
                    sa.Column("value", sa.Text(), nullable=False),
                    sa.CheckConstraint("name ~ '^[A-Z][A-Z0-9_]{0,99}$'", name="ck_configuration_name"))
    op.create_table("permissions", sa.Column("code", sa.String(100), primary_key=True), sa.Column("name", sa.String(150), nullable=False))
    op.create_table("roles", sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True), sa.Column("name", sa.String(100), nullable=False, unique=True))
    op.create_table("role_permissions", sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
                    sa.Column("permission_code", sa.String(100), sa.ForeignKey("permissions.code", ondelete="RESTRICT"), primary_key=True))
    op.add_column("accounts", sa.Column("name", sa.String(255)))
    op.add_column("accounts", sa.Column("contact", sa.String(100)))
    op.add_column("accounts", sa.Column("assigned_role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="RESTRICT")))
    op.add_column("accounts", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("employee_denials", sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True),
                    sa.Column("permission_code", sa.String(100), sa.ForeignKey("permissions.code", ondelete="RESTRICT"), primary_key=True))
    permissions = {
        "DOCUMENTS_READ": "Consultar documentos y bandejas", "DOCUMENTS_UPLOAD": "Cargar documentos",
        "DOCUMENTS_PROCESS": "Ejecutar análisis", "DOCUMENTS_REVIEW": "Resolver revisión humana",
        "DOCUMENTS_DELETE": "Eliminar documentos", "PATIENTS_READ": "Consultar pacientes",
        "PATIENTS_EDIT": "Editar pacientes", "DESTINATIONS_READ": "Consultar destinos",
        "DESTINATIONS_MANAGE": "Administrar destinos y reglas",
    }
    for code, name in permissions.items():
        op.execute(sa.text("INSERT INTO permissions(code,name) VALUES (:code,:name)").bindparams(code=code, name=name))
    for name, codes in {
        "Operador": ["DOCUMENTS_READ", "DOCUMENTS_UPLOAD", "DOCUMENTS_PROCESS", "PATIENTS_READ", "DESTINATIONS_READ"],
        "Revisor": ["DOCUMENTS_READ", "DOCUMENTS_REVIEW", "PATIENTS_READ", "DESTINATIONS_READ"],
        "Administrador operativo": list(permissions),
    }.items():
        op.execute(sa.text("INSERT INTO roles(name) VALUES (:name)").bindparams(name=name))
        for code in codes:
            op.execute(sa.text("INSERT INTO role_permissions(role_id,permission_code) SELECT id,:code FROM roles WHERE name=:name").bindparams(code=code,name=name))


def downgrade():
    op.drop_table("employee_denials")
    for name in ("active", "assigned_role_id", "contact", "name"):
        op.drop_column("accounts", name)
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
    op.drop_table("configuration_variables")
