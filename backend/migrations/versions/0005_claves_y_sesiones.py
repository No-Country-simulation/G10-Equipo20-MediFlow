"""clave de las cuentas y sesiones abiertas

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('clave_hash', sa.String(length=255), nullable=True))

    op.create_table('sesiones',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('expira_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('creada_en', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name='fk_sesiones_usuario', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token_hash')
    )
    with op.batch_alter_table('sesiones', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sesiones_usuario_id'), ['usuario_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('sesiones', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sesiones_usuario_id'))
    op.drop_table('sesiones')
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_column('clave_hash')
