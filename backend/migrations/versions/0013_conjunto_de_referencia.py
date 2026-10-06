"""conjunto de referencia seudonimizado: cada correccion humana

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-06 23:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('casos_referencia',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('correccion_id', sa.Integer(), nullable=False),
    sa.Column('documento_id', sa.String(length=128), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('origen', sa.String(length=16), nullable=False),
    sa.Column('campo', sa.String(length=256), nullable=False),
    sa.Column('extraido', sa.JSON(), nullable=True),
    sa.Column('corregido', sa.JSON(), nullable=True),
    sa.Column('usuario', sa.String(length=128), nullable=False),
    sa.Column('tipo_documento', sa.String(length=64), nullable=True),
    sa.Column('canal_origen', sa.String(length=32), nullable=False),
    sa.Column('pais', sa.String(length=2), nullable=False),
    sa.Column('texto_seudonimizado', sa.Text(), nullable=True),
    sa.Column('propuesta_json', sa.JSON(), nullable=True),
    sa.Column('nivel_propuesto', sa.String(length=16), nullable=True),
    sa.Column('nivel_antes', sa.String(length=16), nullable=True),
    sa.Column('nivel_resultante', sa.String(length=16), nullable=True),
    sa.Column('hallazgos_json', sa.JSON(), nullable=True),
    sa.Column('modelo_llm', sa.String(length=64), nullable=True),
    sa.Column('version_prompt', sa.String(length=32), nullable=True),
    sa.Column('version_reglas', sa.String(length=16), nullable=True),
    sa.Column('version_pack', sa.String(length=16), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['correccion_id'], ['correcciones.id'], name='fk_referencia_correccion'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('correccion_id')
    )
    with op.batch_alter_table('casos_referencia', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_casos_referencia_documento_id'), ['documento_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_casos_referencia_campo'), ['campo'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('casos_referencia', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_casos_referencia_campo'))
        batch_op.drop_index(batch_op.f('ix_casos_referencia_documento_id'))
    op.drop_table('casos_referencia')
