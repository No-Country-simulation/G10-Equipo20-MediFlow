"""cola persistente de procesamiento: trabajos con arriendo para un worker aparte

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-07 20:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('trabajos_procesamiento',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('documento_pk', sa.Integer(), nullable=False),
    sa.Column('documento_id', sa.String(length=128), nullable=False),
    sa.Column('estado', sa.String(length=16), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('proximo_intento_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('arrendado_hasta', sa.DateTime(timezone=True), nullable=True),
    sa.Column('token', sa.String(length=36), nullable=True),
    sa.Column('intento', sa.Integer(), nullable=False),
    sa.Column('codigo_error', sa.String(length=300), nullable=True),
    sa.Column('solicitado_por', sa.String(length=128), nullable=True),
    sa.ForeignKeyConstraint(['documento_pk'], ['documentos.id']),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_trabajos_procesamiento_documento_pk'), 'trabajos_procesamiento', ['documento_pk'], unique=False)
    op.create_index('ix_trabajo_vivo_por_documento', 'trabajos_procesamiento', ['documento_pk'], unique=True,
                    postgresql_where=sa.text("estado IN ('EN_COLA', 'EN_CURSO')"))


def downgrade() -> None:
    op.drop_index('ix_trabajo_vivo_por_documento', table_name='trabajos_procesamiento')
    op.drop_index(op.f('ix_trabajos_procesamiento_documento_pk'), table_name='trabajos_procesamiento')
    op.drop_table('trabajos_procesamiento')
