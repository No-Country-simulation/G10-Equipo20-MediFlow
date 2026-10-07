"""Add jobs, documentary policies, integrity and backup outbox."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_persistent_processing"
down_revision = "0010_administration"
branch_labels = depends_on = None


def upgrade():
    op.drop_constraint("ck_documents_format", "documents")
    op.create_check_constraint("ck_documents_format", "documents", "format IN ('pdf','jpeg','png','text')")
    op.add_column("documents", sa.Column("sha256", sa.String(64)))
    op.add_column("documents", sa.Column("origin_channel", sa.String(100)))
    op.create_table("processing_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)), sa.Column("token", sa.Uuid()),
        sa.Column("active_node", sa.String(50)), sa.Column("completed_nodes", postgresql.JSONB(), nullable=False),
        sa.Column("provider_calls", postgresql.JSONB(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False), sa.Column("error_code", sa.String(100)),
        sa.Column("policy_snapshot", postgresql.JSONB()))
    op.create_index("ix_processing_jobs_active_document", "processing_jobs", ["document_id"], unique=True,
                    postgresql_where=sa.text("status IN ('QUEUED','RUNNING')"))
    op.create_table("document_policies", sa.Column("document_type", sa.String(50), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("result_backups", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(255), unique=True, nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=False), sa.Column("error_code", sa.String(100)))
    op.create_index("ix_result_backups_document_id", "result_backups", ["document_id"])
    from app.core.document_catalog import REQUIRED_GROUPS
    import json
    for kind, groups in REQUIRED_GROUPS.items():
        config = {"required_groups": groups, "weights": {"readability": .25, "completeness": .30, "evidence": .30, "consistency": .15}, "threshold": .85}
        op.execute(sa.text("INSERT INTO document_policies VALUES (:kind,1,CAST(:config AS jsonb),CURRENT_TIMESTAMP)")
                   .bindparams(kind=kind, config=json.dumps(config)))


def downgrade():
    op.drop_table("result_backups")
    op.drop_table("document_policies")
    op.drop_table("processing_jobs")
    op.drop_column("documents", "origin_channel")
    op.drop_column("documents", "sha256")
    # Refuse to silently discard text documents on downgrade.
    op.drop_constraint("ck_documents_format", "documents")
    op.create_check_constraint("ck_documents_format", "documents", "format IN ('pdf','jpeg','png')")
