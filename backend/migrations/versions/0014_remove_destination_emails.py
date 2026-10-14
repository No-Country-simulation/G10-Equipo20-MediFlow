"""Remove unsupported destination email notifications."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0014_remove_destination_emails'
down_revision = '0013_destination_contacts'
branch_labels = depends_on = None


def upgrade():
    op.drop_column('destinations', 'emails')


def downgrade():
    op.add_column('destinations', sa.Column('emails', postgresql.JSONB(), nullable=False,
                                          server_default=sa.text("'[]'::jsonb")))
