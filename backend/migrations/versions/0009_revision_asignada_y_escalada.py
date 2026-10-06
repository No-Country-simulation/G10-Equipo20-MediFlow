"""revision humana: a quien esta asignado cada caso y a que rol se escalo

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-06 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('asignado_a', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('escalado_a_rol', sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.drop_column('escalado_a_rol')
        batch_op.drop_column('asignado_a')
