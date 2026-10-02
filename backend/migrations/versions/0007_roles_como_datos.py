"""roles como datos (tabla K) y ultimo ingreso de cada cuenta

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-02 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

from app.services.roles_base import ROLES_BASE


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    roles = op.create_table('roles',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=64), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=False),
    sa.Column('ve', sa.String(length=128), nullable=False),
    sa.Column('puede', sa.String(length=128), nullable=False),
    sa.Column('secciones', sa.JSON(), nullable=False),
    sa.Column('acciones', sa.JSON(), nullable=False),
    sa.Column('tipos_documento', sa.JSON(), nullable=False),
    sa.Column('ve_documentos', sa.Boolean(), nullable=False),
    sa.Column('ruta_inicial', sa.String(length=64), nullable=False),
    sa.Column('modo_discreto', sa.Boolean(), nullable=False),
    sa.Column('alto_contraste', sa.Boolean(), nullable=False),
    sa.Column('pantalla_compartida', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.bulk_insert(roles, ROLES_BASE)
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ultimo_ingreso_en', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_column('ultimo_ingreso_en')
    op.drop_table('roles')
