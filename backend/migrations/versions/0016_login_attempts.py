"""Persist failed-login limits across API restarts and workers."""
from alembic import op
import sqlalchemy as sa

revision = '0016_login_attempts'
down_revision = '0015_email_notifications'
branch_labels = depends_on = None


def upgrade():
    op.create_table('login_attempts',
        sa.Column('identity_hash', sa.String(64), primary_key=True),
        sa.Column('failures', sa.Integer(), nullable=False),
        sa.Column('window_started', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('login_attempts')
