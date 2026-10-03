"""cuentas de producto: clave inicial por cambiar, bloqueo por intentos, eventos de sesion y tipo del documento en su fila

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-02 21:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('debe_cambiar_clave', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('intentos_fallidos', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('bloqueado_hasta', sa.DateTime(timezone=True), nullable=True))
    # Toda cuenta sembrada por la instalación tiene una clave que no eligió su dueño: se cambia en el primer ingreso.
    op.execute("UPDATE usuarios SET debe_cambiar_clave = true WHERE creado_por = 'instalacion' AND rol <> 'administrador'")

    op.create_table('eventos_sesion',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('usuario', sa.String(length=128), nullable=False),
    sa.Column('evento', sa.String(length=32), nullable=False),
    sa.Column('detalle', sa.String(length=256), nullable=False),
    sa.Column('fecha_hora', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('eventos_sesion', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_eventos_sesion_usuario'), ['usuario'], unique=False)

    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tipo', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_documentos_tipo'), ['tipo'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documentos_tipo'))
        batch_op.drop_column('tipo')
    with op.batch_alter_table('eventos_sesion', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_eventos_sesion_usuario'))
    op.drop_table('eventos_sesion')
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_column('bloqueado_hasta')
        batch_op.drop_column('intentos_fallidos')
        batch_op.drop_column('debe_cambiar_clave')
