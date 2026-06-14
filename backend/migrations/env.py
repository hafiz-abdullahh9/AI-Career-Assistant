"""
Alembic environment configuration for async SQLAlchemy.

Supports:
  - Online mode: connected to a live database (default)
  - Offline mode: generates SQL scripts without a live connection

Uses the DATABASE_URL from the application settings so the same
.env file controls both the app and migrations.
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, engine_from_config
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import the declarative base so Alembic can auto-detect models
from app.core.database import Base
from app.core.config import get_settings

# Import all models so they register with Base.metadata
import app.models.orm  # noqa: F401

# Alembic Config object
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point Alembic at our models' metadata for auto-generation
target_metadata = Base.metadata

# Override sqlalchemy.url from settings (so .env is the single source of truth)
# Override sqlalchemy.url from settings (so .env is the single source of truth)
settings = get_settings()
# Ensure the URL uses a synchronous driver for migrations (psycopg2)
sync_url = settings.database_url.replace('+asyncpg', '+psycopg2')
config.set_main_option('sqlalchemy.url', sync_url)


def run_migrations_offline() -> None:
    """
    Run migrations in offline mode.

    Generates SQL scripts without requiring a live DB connection.
    Useful for reviewing or applying migrations manually.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode using a synchronous engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
