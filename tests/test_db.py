"""Unit tests for guild.db URL coercion.

These tests are pure-Python and require no database connection.
"""
import pytest

from guild.db import _coerce_psycopg3


@pytest.mark.parametrize(
    "input_url, expected",
    [
        # Render / Heroku short form → psycopg3 dialect
        (
            "postgres://user:pass@host/db",
            "postgresql+psycopg://user:pass@host/db",
        ),
        # Long form without explicit driver → psycopg3 dialect
        (
            "postgresql://user:pass@host/db",
            "postgresql+psycopg://user:pass@host/db",
        ),
        # Already correct — must not be double-coerced
        (
            "postgresql+psycopg://user:pass@host/db",
            "postgresql+psycopg://user:pass@host/db",
        ),
        # Explicit psycopg2 URL — must NOT be silently rewritten
        (
            "postgresql+psycopg2://user:pass@host/db",
            "postgresql+psycopg2://user:pass@host/db",
        ),
    ],
)
def test_coerce_psycopg3(input_url: str, expected: str) -> None:
    assert _coerce_psycopg3(input_url) == expected
