"""Patient identity registry and nullable document association."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_patients"
down_revision = "0006_destinations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "patients",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("identity_type", sa.String(16), nullable=False),
        sa.Column("identity_number", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("age", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audit_history", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.UniqueConstraint("country", "identity_type", "identity_number", name="uq_patient_identity"),
    )
    op.add_column("documents", sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id", ondelete="SET NULL")))
    op.add_column("documents", sa.Column("patient_match_status", sa.String(24), nullable=False,
                                          server_default="NOT_EVALUATED"))
    op.add_column("documents", sa.Column("patient_match_reason", sa.String(100)))
    op.create_index("ix_documents_patient_id", "documents", ["patient_id"])


def downgrade():
    op.drop_index("ix_documents_patient_id", table_name="documents")
    op.drop_column("documents", "patient_match_reason")
    op.drop_column("documents", "patient_match_status")
    op.drop_column("documents", "patient_id")
    op.drop_table("patients")
