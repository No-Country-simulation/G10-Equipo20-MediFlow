"""solicitudes del titular: revision humana de una decision automatizada

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-06 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('solicitudes_titular',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('paciente_id', sa.Integer(), nullable=False),
    sa.Column('documento_id', sa.String(length=128), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('presentada_por', sa.String(length=16), nullable=False),
    sa.Column('canal', sa.String(length=16), nullable=False),
    sa.Column('motivo', sa.Text(), nullable=False),
    sa.Column('registrada_por', sa.String(length=128), nullable=False),
    sa.Column('registrada_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('vence_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('estado', sa.String(length=16), nullable=False),
    sa.Column('resultado', sa.String(length=16), nullable=True),
    sa.Column('respuesta', sa.Text(), nullable=True),
    sa.Column('respondida_por', sa.String(length=128), nullable=True),
    sa.Column('respondida_en', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['paciente_id'], ['pacientes.id'], name='fk_solicitudes_paciente'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('solicitudes_titular', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_solicitudes_titular_paciente_id'), ['paciente_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_solicitudes_titular_documento_id'), ['documento_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_solicitudes_titular_estado'), ['estado'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('solicitudes_titular', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_solicitudes_titular_estado'))
        batch_op.drop_index(batch_op.f('ix_solicitudes_titular_documento_id'))
        batch_op.drop_index(batch_op.f('ix_solicitudes_titular_paciente_id'))
    op.drop_table('solicitudes_titular')
