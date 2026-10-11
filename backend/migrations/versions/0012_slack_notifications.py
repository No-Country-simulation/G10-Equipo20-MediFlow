"""Persist Slack delivery independently from documentary processing."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0012_slack_notifications'
down_revision = '0011_persistent_processing'
branch_labels = depends_on = None


def upgrade():
    op.create_table('slack_notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('document_id', sa.Uuid(), sa.ForeignKey('documents.document_id', ondelete='CASCADE'), nullable=False),
        sa.Column('level', sa.String(10), nullable=False), sa.Column('status', sa.String(20), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False), sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('retryable', sa.Boolean(), nullable=False),
        sa.Column('retry_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True)), sa.Column('error_code', sa.String(80)),
        sa.UniqueConstraint('document_id', 'level', name='uq_slack_document_level'))
    op.create_index('ix_slack_notifications_document_id', 'slack_notifications', ['document_id'])


def downgrade():
    op.drop_table('slack_notifications')
