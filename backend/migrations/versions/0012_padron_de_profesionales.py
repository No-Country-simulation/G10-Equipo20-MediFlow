"""padron de profesionales de la instalacion

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-06 21:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('profesionales',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('registro', sa.String(length=32), nullable=False),
    sa.Column('nombre', sa.String(length=255), nullable=False),
    sa.Column('profesion', sa.String(length=64), nullable=True),
    sa.Column('tipo_documento', sa.String(length=8), nullable=True),
    sa.Column('numero_documento', sa.String(length=32), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('registro_consultado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('registro_consultado_por', sa.String(length=128), nullable=True),
    sa.Column('creado_por', sa.String(length=128), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('profesionales', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profesionales_registro'), ['registro'], unique=True)
        batch_op.create_index(batch_op.f('ix_profesionales_numero_documento'), ['numero_documento'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('profesionales', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profesionales_numero_documento'))
        batch_op.drop_index(batch_op.f('ix_profesionales_registro'))
    op.drop_table('profesionales')
