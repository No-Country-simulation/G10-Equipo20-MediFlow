"""Locate each original independently of the current upload backend."""
from alembic import op
import sqlalchemy as sa

revision = "0004_storage_country"
down_revision = "0003_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("storage_backend", sa.String(10), nullable=False, server_default="local"))
    op.add_column("documents", sa.Column("storage_bucket", sa.String(63), nullable=True))
    op.add_column("documents", sa.Column("country", sa.String(2), nullable=False, server_default="EC"))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM documents WHERE storage_backend <> 'local'")):
        raise RuntimeError("R2 documents must retain their storage locator.")
    for column in ("country", "storage_bucket", "storage_backend"):
        op.drop_column("documents", column)
