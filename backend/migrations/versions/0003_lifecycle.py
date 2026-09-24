"""Estados documentales, rechazos auditables e historial."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_lifecycle"
down_revision = "0002_processing"
branch_labels = None
depends_on = None

STATES = "'RECIBIDO', 'VALIDADO', 'CLASIFICADO', 'EXTRAIDO', 'EVALUADO', 'ENRUTADO', 'ENTREGADO', 'RECHAZADO', 'FALLO_TECNICO', 'EN_REVISION_HUMANA', 'RESUELTO'"


def upgrade():
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.drop_constraint("ck_documents_size_positive", "documents", type_="check")
    op.alter_column("documents", "format", existing_type=sa.String(4), nullable=True)
    op.alter_column("documents", "size_bytes", existing_type=sa.Integer(), nullable=True)
    op.alter_column("documents", "storage_key", existing_type=sa.String(80), nullable=True)
    op.add_column("documents", sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("rejection_reason", sa.String(255), nullable=True))
    op.add_column("documents", sa.Column("state_history", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("documents", sa.Column("review_history", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.execute("""UPDATE documents SET status = CASE status
        WHEN 'UPLOADED' THEN 'VALIDADO' WHEN 'COMPLETED' THEN 'EVALUADO'
        WHEN 'HUMAN_REVIEW' THEN 'EN_REVISION_HUMANA' ELSE 'FALLO_TECNICO' END,
        processing_attempts = CASE WHEN processing_result IS NULL THEN 0 ELSE 1 END""")
    op.execute("""UPDATE documents SET processing_result = jsonb_set(processing_result, '{status}', to_jsonb(status))
        WHERE processing_result IS NOT NULL""")
    # Registrar lo que se conoce sin inventar etapas historicas intermedias.
    op.execute("""UPDATE documents SET state_history = jsonb_build_array(jsonb_build_object(
        'status', status, 'occurred_at', now(), 'reason', 'MIGRATED_FROM_V1', 'attempt', processing_attempts))""")
    op.create_check_constraint("ck_documents_status", "documents", f"status IN ({STATES})")
    op.create_check_constraint("ck_documents_size_positive", "documents", "size_bytes >= 0")


def downgrade():
    raise RuntimeError("Migracion con historial y rechazos: revertir requiere un plan explicito para conservar los datos.")
