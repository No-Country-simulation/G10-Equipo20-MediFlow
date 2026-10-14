"""Restore destination recipients and prepare an opt-in SMTP outbox."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0015_email_notifications'
down_revision = '0014_remove_destination_emails'
branch_labels = depends_on = None


def upgrade():
    op.add_column('destinations', sa.Column('emails', postgresql.JSONB(), nullable=False,
                                          server_default=sa.text("'[]'::jsonb")))
    op.create_table('email_notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('document_id', sa.Uuid(), sa.ForeignKey('documents.document_id', ondelete='CASCADE'), nullable=False),
        sa.Column('destination_code', sa.String(60), sa.ForeignKey('destinations.code', ondelete='RESTRICT'), nullable=False),
        sa.Column('event', sa.String(10), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('retry_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True)),
        sa.Column('error_code', sa.String(80)),
        sa.UniqueConstraint('document_id', 'event', name='uq_email_document_event'))
    op.create_index('ix_email_notifications_document_id', 'email_notifications', ['document_id'])


def downgrade():
    op.drop_table('email_notifications')
    op.drop_column('destinations', 'emails')
