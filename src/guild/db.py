"""Database engine and session factory.

The application entry point (guild.main, Slice 5) calls make_engine() with
the DATABASE_URL from load_config().  Tests construct engines directly from
the test DATABASE_URL without going through load_config().

Render (and Heroku) supply DATABASE_URL with a ``postgres://`` or
``postgresql://`` scheme.  SQLAlchemy routes those to psycopg2 by default,
but this project depends on psycopg3 (``psycopg>=3.1``).  We coerce the URL
to the explicit ``postgresql+psycopg://`` scheme before SQLAlchemy sees it.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _coerce_psycopg3(url: str) -> str:
    """Coerce a Render/Heroku-style DATABASE_URL to use the psycopg3 dialect.

    SQLAlchemy maps ``postgres://`` and ``postgresql://`` to psycopg2 by
    default.  This project uses psycopg3 (``psycopg``), so we rewrite those
    prefixes to the explicit ``postgresql+psycopg://`` driver URL.

    URLs that already carry an explicit driver (e.g.
    ``postgresql+psycopg://`` or ``postgresql+psycopg2://``) are returned
    unchanged so that tests and local overrides are never silently mutated.
    """
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    # already has an explicit driver — leave alone
    return url


def make_engine(database_url: str):
    """Create a SQLAlchemy engine for the given database URL."""
    return create_engine(_coerce_psycopg3(database_url))


def make_session_factory(engine) -> sessionmaker[Session]:
    """Create a sessionmaker bound to the given engine."""
    return sessionmaker(engine)
