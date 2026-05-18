"""Database engine and session factory.

The application entry point (guild.main, Slice 5) calls make_engine() with
the DATABASE_URL from load_config().  Tests construct engines directly from
the test DATABASE_URL without going through load_config().
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(database_url: str):
    """Create a SQLAlchemy engine for the given database URL."""
    return create_engine(database_url)


def make_session_factory(engine) -> sessionmaker[Session]:
    """Create a sessionmaker bound to the given engine."""
    return sessionmaker(engine)
