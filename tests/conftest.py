import os

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine

_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://guild:guild@localhost:5432/guild_test",
)


@pytest.fixture(scope="session")
def db_engine():
    """Session-scoped engine.  Runs Alembic migrations once per test run."""
    engine = create_engine(_DATABASE_URL)
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", _DATABASE_URL)
    alembic_command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    """Per-test database connection that always rolls back on teardown.

    Tests get a real Postgres connection and the full live schema.  The
    unconditional rollback means each test starts with a clean slate without
    needing to truncate tables.
    """
    conn = db_engine.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()
