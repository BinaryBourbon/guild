import os

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://guild:guild@localhost:5432/guild_test",
)


@pytest.fixture(scope="session")
def db_engine():
    """Session-scoped engine. Runs Alembic migrations once per test run."""
    engine = create_engine(_DATABASE_URL)
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", _DATABASE_URL)
    alembic_command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    """Per-test raw Connection with always-rollback teardown.

    Use for raw SQL tests (test_schema.py).  For ORM tests use `session`.
    """
    conn = db_engine.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


@pytest.fixture
def session(db_engine):
    """Per-test ORM Session with always-rollback teardown.

    Tests MUST use session.flush() (not session.commit()) to push changes
    to the DB within the test.  The rollback in teardown provides isolation.
    """
    factory = sessionmaker(db_engine)
    sess = factory()
    try:
        yield sess
    finally:
        sess.rollback()
        sess.close()
