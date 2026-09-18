"""Metadatos de documentos recibidos."""
from alembic import op
import sqlalchemy as sa

revision = "0001_documents"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "documents",
        sa.Column("document_id", sa.Uuid(), primary_key=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("format", sa.String(4), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("storage_key", sa.String(80), nullable=False, unique=True),
        sa.CheckConstraint("size_bytes > 0", name="ck_documents_size_positive"),
        sa.CheckConstraint("format IN ('pdf', 'jpeg', 'png')", name="ck_documents_format"),
        sa.CheckConstraint("status = 'UPLOADED'", name="ck_documents_status"),
    )


def downgrade():
    op.drop_table("documents")
