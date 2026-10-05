"""formato del documento con espacio para 'desconocido'

Un archivo rechazado guarda formato 'desconocido' (11 caracteres); con 8, PostgreSQL rechazaba el INSERT.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.alter_column('formato', existing_type=sa.String(length=8), type_=sa.String(length=16), existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.alter_column('formato', existing_type=sa.String(length=16), type_=sa.String(length=8), existing_nullable=True)
