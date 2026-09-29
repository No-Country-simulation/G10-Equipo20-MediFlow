"""Local accounts and laboratory routes."""
from alembic import op
import sqlalchemy as sa

revision = "0008_accounts_laboratory"
down_revision = "0007_patients"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("accounts",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("country", sa.String(2)),
        sa.Column("identity_type", sa.String(16)),
        sa.Column("identity_number", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("country", "identity_type", "identity_number", name="uq_account_identity"))
    op.create_table("login_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.execute("INSERT INTO routing_rules (document_type, specialty, destination_code, active) VALUES "
               "('LABORATORY_ORDER', 'ANY', 'LABORATORIO', true), "
               "('LABORATORY_RESULT', 'ANY', 'HISTORIA_CLINICA', true) "
               "ON CONFLICT (document_type, specialty) DO NOTHING")


def downgrade():
    op.execute("DELETE FROM routing_rules WHERE document_type IN ('LABORATORY_ORDER', 'LABORATORY_RESULT')")
    op.drop_table("login_sessions")
    op.drop_table("accounts")
