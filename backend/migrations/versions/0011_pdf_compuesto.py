"""pdf compuesto: cada sub-documento lleva su documento padre

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-06 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('documento_padre', sa.String(length=128), nullable=True))
        batch_op.create_index(batch_op.f('ix_documentos_documento_padre'), ['documento_padre'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documentos_documento_padre'))
        batch_op.drop_column('documento_padre')
