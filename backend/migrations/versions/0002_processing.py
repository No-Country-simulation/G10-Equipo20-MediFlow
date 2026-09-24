"""Resultado documental y estados de procesamiento."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_processing"
down_revision = "0001_documents"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_status", "documents",
        "status IN ('UPLOADED', 'PROCESSING', 'COMPLETED', 'HUMAN_REVIEW', 'FAILED')",
    )
    op.add_column("documents", sa.Column("processing_result", postgresql.JSONB(), nullable=True))


def downgrade():
    # Evitar una perdida silenciosa de resultados al revertir.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM documents WHERE processing_result IS NOT NULL")):
        raise RuntimeError("Existen resultados de procesamiento; conservarlos antes de revertir.")
    op.drop_column("documents", "processing_result")
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.create_check_constraint("ck_documents_status", "documents", "status = 'UPLOADED'")
