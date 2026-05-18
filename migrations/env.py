import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from guild.db import _coerce_psycopg3

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 12-factor: DATABASE_URL from environment overrides whatever is in alembic.ini.
# Coerce to psycopg3 dialect so Render/Heroku-style postgres:// URLs work.
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", _coerce_psycopg3(database_url))


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
