"""directorio de pacientes y vinculo con documentos

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('pacientes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('pais', sa.String(length=2), nullable=False),
    sa.Column('tipo_documento', sa.String(length=16), nullable=False),
    sa.Column('numero_documento', sa.String(length=32), nullable=False),
    sa.Column('nombre', sa.String(length=255), nullable=False),
    sa.Column('edad', sa.Integer(), nullable=True),
    sa.Column('sexo', sa.String(length=16), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('historial_json', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('pais', 'tipo_documento', 'numero_documento', name='uq_paciente_identidad')
    )
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pacientes_numero_documento'), ['numero_documento'], unique=False)

    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('paciente_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_documentos_paciente_id'), ['paciente_id'], unique=False)
        batch_op.create_foreign_key('fk_documentos_paciente', 'pacientes', ['paciente_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.drop_constraint('fk_documentos_paciente', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_documentos_paciente_id'))
        batch_op.drop_column('paciente_id')

    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pacientes_numero_documento'))
    op.drop_table('pacientes')
