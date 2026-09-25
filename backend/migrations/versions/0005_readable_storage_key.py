"""Allow UUID and descriptive filename in storage keys."""
from alembic import op
import sqlalchemy as sa
revision = "0005_readable_storage_key"
down_revision = "0004_storage_country"
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column("documents", "storage_key", existing_type=sa.String(80), type_=sa.String(255))

def downgrade():
    # Explicitly refuse truncation of live object locators.
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM documents WHERE length(storage_key) > 80) THEN RAISE EXCEPTION 'Storage keys exceed 80 characters'; END IF; END $$")
    op.alter_column("documents", "storage_key", existing_type=sa.String(255), type_=sa.String(80))
