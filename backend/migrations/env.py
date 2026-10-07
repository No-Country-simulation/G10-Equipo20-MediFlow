from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.models.document import Base
from app.models import destination  # noqa: F401 - register catalog tables
from app.models import patient  # noqa: F401 - register patient table
from app.models import account  # noqa: F401 - register account tables
from app.models import administration  # noqa: F401
from app.models import execution  # noqa: F401

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(get_settings().database_url, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
