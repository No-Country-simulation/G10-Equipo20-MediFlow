"""gobierno: versiones de configuracion, usuarios y accesos

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-26 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('versiones_configuracion',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('numero', sa.Integer(), nullable=True),
    sa.Column('autor', sa.String(length=128), nullable=False),
    sa.Column('motivo', sa.Text(), nullable=False),
    sa.Column('cambios_json', sa.JSON(), nullable=False),
    sa.Column('simulacion_json', sa.JSON(), nullable=True),
    sa.Column('toca_seguridad', sa.Boolean(), nullable=False),
    sa.Column('aprobaciones_json', sa.JSON(), nullable=False),
    sa.Column('estado', sa.String(length=16), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('vigente_desde', sa.DateTime(timezone=True), nullable=True),
    sa.Column('vigente_hasta', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cierre_por', sa.String(length=128), nullable=True),
    sa.Column('cierre_motivo', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('versiones_configuracion', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_versiones_configuracion_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_versiones_configuracion_numero'), ['numero'], unique=False)

    op.create_table('usuarios',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('usuario', sa.String(length=128), nullable=False),
    sa.Column('nombre', sa.String(length=256), nullable=False),
    sa.Column('rol', sa.String(length=32), nullable=False),
    sa.Column('tipo', sa.String(length=16), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('creado_por', sa.String(length=128), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('desactivado_en', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_usuarios_usuario'), ['usuario'], unique=True)

    op.create_table('accesos_documento',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('documento_id', sa.String(length=128), nullable=False),
    sa.Column('usuario', sa.String(length=128), nullable=False),
    sa.Column('accion', sa.String(length=32), nullable=False),
    sa.Column('fecha_hora', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('accesos_documento', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_accesos_documento_documento_id'), ['documento_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_accesos_documento_usuario'), ['usuario'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('accesos_documento', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_accesos_documento_usuario'))
        batch_op.drop_index(batch_op.f('ix_accesos_documento_documento_id'))
    op.drop_table('accesos_documento')
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_usuarios_usuario'))
    op.drop_table('usuarios')
    with op.batch_alter_table('versiones_configuracion', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_versiones_configuracion_numero'))
        batch_op.drop_index(batch_op.f('ix_versiones_configuracion_estado'))
    op.drop_table('versiones_configuracion')
