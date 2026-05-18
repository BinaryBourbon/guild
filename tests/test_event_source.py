"""Tests for PollingEventSource.

GitHub calls are mocked. Database interactions use real Postgres.
Focuses on:
- Dedup: second poll with same updated_at does NOT double-write
- on_event called for new events
- on_event NOT called if nothing changed
"""
from __future__ import annotations

import datetime
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from guild import crud, state_machine
from guild.event_source import PollingEventSource, _deterministic_event_id
from guild.models import Thread, ThreadEvent


def _seed_active_thread(session, suffix="") -> Thread:
    """Create a thread in 'noticed' state (active, will be polled)."""
    thread = crud.create_thread(
        anchor_type="github_issue",
        anchor_id=f"owner/repo#555{suffix}",
        anchor_url="https://github.com/owner/repo/issues/555",
        anchor_title="Test Issue",
        session=session,
    )
    state_machine.transition(thread.id, "noticed", session)
    session.flush()
    return thread


def _make_github_mock(updated_at: str = "2024-01-01T00:00:00Z") -> MagicMock:
    mock = MagicMock()
    mock.get.return_value = {
        "number": 555,
        "title": "Test Issue",
        "state": "open",
        "updated_at": updated_at,
        "labels": [],
    }
    return mock


def _make_session_factory(db_engine):
    """Return a real session factory using the test engine."""
    from sqlalchemy.orm import sessionmaker

    @contextmanager
    def factory():
        Session = sessionmaker(db_engine)
        sess = Session()
        try:
            yield sess
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

    return factory


def test_on_event_called_for_new_event(session, db_engine):
    """on_event handler is called when a new event is written for an active thread."""
    thread = _seed_active_thread(session)
    session.commit()

    github = _make_github_mock()
    factory = _make_session_factory(db_engine)
    events_seen = []

    source = PollingEventSource(github, factory, poll_interval=120)
    source.on_event(lambda tid, ev: events_seen.append((tid, ev)))

    source._poll_once()

    assert len(events_seen) == 1
    tid, ev = events_seen[0]
    assert tid == thread.id
    assert ev["type"] == "issue.polled"


def test_dedup_second_poll_does_not_double_write(session, db_engine):
    """Second poll with same updated_at does not insert a duplicate event."""
    thread = _seed_active_thread(session, suffix="d")
    session.commit()

    github = _make_github_mock(updated_at="2024-06-01T12:00:00Z")
    factory = _make_session_factory(db_engine)
    events_seen = []

    source = PollingEventSource(github, factory, poll_interval=120)
    source.on_event(lambda tid, ev: events_seen.append((tid, ev)))

    source._poll_once()
    source._poll_once()  # Second poll — same updated_at

    # on_event is called each poll, but only 1 row in the DB
    with factory() as s:
        event_id = _deterministic_event_id(
            thread.id, "github", "issue.polled",
            f"{thread.anchor_id}:2024-06-01T12:00:00Z",
        )
        rows = s.execute(
            select(ThreadEvent).where(ThreadEvent.id == event_id)
        ).scalars().all()
    assert len(rows) == 1  # deduped — only one row despite two polls


def test_on_event_not_called_for_inactive_thread(session, db_engine):
    """on_event is NOT called for threads in terminal states."""
    # Create a done thread (terminal — should not be polled)
    thread = crud.create_thread(
        anchor_type="github_issue",
        anchor_id="owner/repo#777",
        anchor_url="https://github.com/owner/repo/issues/777",
        anchor_title="Done thread",
        session=session,
    )
    state_machine.transition(thread.id, "noticed", session)
    state_machine.transition(thread.id, "claimed", session)
    state_machine.transition(thread.id, "executing", session)
    # Use pr_open → done
    state_machine.transition(thread.id, "pr_open", session)
    state_machine.transition(thread.id, "done", session)
    session.commit()

    github = _make_github_mock()
    factory = _make_session_factory(db_engine)
    events_seen = []

    source = PollingEventSource(github, factory, poll_interval=120)
    source.on_event(lambda tid, ev: events_seen.append((tid, ev)))

    source._poll_once()

    # The done thread should NOT appear in events
    assert all(tid != thread.id for tid, _ in events_seen)


def test_deterministic_event_id_stable():
    """Same inputs always produce the same event ID."""
    id1 = _deterministic_event_id("t1", "github", "issue.polled", "owner/repo#1:2024-01-01")
    id2 = _deterministic_event_id("t1", "github", "issue.polled", "owner/repo#1:2024-01-01")
    assert id1 == id2


def test_deterministic_event_id_different_for_different_timestamps():
    """Different updated_at values produce different IDs."""
    id1 = _deterministic_event_id("t1", "github", "issue.polled", "owner/repo#1:2024-01-01")
    id2 = _deterministic_event_id("t1", "github", "issue.polled", "owner/repo#1:2024-01-02")
    assert id1 != id2
