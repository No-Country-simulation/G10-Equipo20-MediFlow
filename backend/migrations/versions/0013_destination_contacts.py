"""Destination notification contacts and Slack outbox targets."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0013_destination_contacts'
down_revision = '0012_slack_notifications'
branch_labels = depends_on = None


def upgrade():
    op.add_column('destinations', sa.Column('slack_webhook_url', sa.String(512), nullable=False, server_default=''))
    op.add_column('destinations', sa.Column('emails', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column('slack_notifications', sa.Column('destination_code', sa.String(60), nullable=True))
    op.create_foreign_key('fk_slack_notification_destination', 'slack_notifications', 'destinations', ['destination_code'], ['code'], ondelete='RESTRICT')


def downgrade():
    op.drop_constraint('fk_slack_notification_destination', 'slack_notifications', type_='foreignkey')
    op.drop_column('slack_notifications', 'destination_code')
    op.drop_column('destinations', 'emails')
    op.drop_column('destinations', 'slack_webhook_url')
