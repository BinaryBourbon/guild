"""Tests for PollingEventSource.

GitHub calls are mocked. Database interactions use real Postgres via db_engine.
Tests that commit data use unique ULID-based anchor IDs so repeated runs
don't collide on the unique (anchor_type, anchor_id) constraint.

Focuses on:
- Dedup: second poll with same updated_at does NOT double-write
- on_event called for new events
- on_event NOT called if nothing changed
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from guild import crud, state_machine
from guild.event_source import PollingEventSource, _deterministic_event_id
from guild.models import Thread, ThreadEvent


def _unique_anchor() -> str:
    """Return a globally unique anchor ID for this test to avoid constraint collisions."""
    return f"owner/repo#test-{uuid.uuid4().hex}"


def _seed_active_thread(session, anchor_id: str) -> Thread:
    """Create a thread in 'noticed' state (active, will be polled)."""
    thread = crud.create_thread(
        anchor_type="github_issue",
        anchor_id=anchor_id,
        anchor_url=f"https://github.com/{anchor_id.replace('#', '/issues/')}",
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


@contextmanager
def _session_ctx(db_engine):
    """Real session with commit support (for tests that need real persistence)."""
    Session = sessionmaker(db_engine)
    sess = Session()
    try:
        yield sess
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


def _make_session_factory(db_engine):
    """Return a context-manager factory producing real sessions from db_engine."""
    @contextmanager
    def factory():
        with _session_ctx(db_engine) as sess:
            yield sess
    return factory


def test_on_event_called_for_new_event(db_engine):
    """on_event handler is called when a new event is written for an active thread."""
    anchor_id = _unique_anchor()
    with _session_ctx(db_engine) as seed_session:
        thread = _seed_active_thread(seed_session, anchor_id)
        thread_id = thread.id  # capture inside session before close
        seed_session.commit()

    github = _make_github_mock()
    factory = _make_session_factory(db_engine)
    events_seen = []

    source = PollingEventSource(github, factory, poll_interval=120)
    source.on_event(lambda tid, ev: events_seen.append((tid, ev)))

    source._poll_once()

    # Filter to only events for this test's thread (other committed threads may exist)
    my_events = [(tid, ev) for tid, ev in events_seen if tid == thread_id]
    assert len(my_events) == 1
    tid, ev = my_events[0]
    assert tid == thread_id
    assert ev["type"] == "issue.polled"


def test_dedup_second_poll_does_not_double_write(db_engine):
    """Second poll with same updated_at does not insert a duplicate event,
    and the on_event handler is called exactly once (not on the duplicate poll)."""
    anchor_id = _unique_anchor()
    with _session_ctx(db_engine) as seed_session:
        thread = _seed_active_thread(seed_session, anchor_id)
        thread_id = thread.id  # capture inside session before close
        seed_session.commit()

    updated_at = "2024-06-01T12:00:00Z"
    github = _make_github_mock(updated_at=updated_at)
    factory = _make_session_factory(db_engine)
    events_seen = []

    source = PollingEventSource(github, factory, poll_interval=120)
    source.on_event(lambda tid, ev: events_seen.append((tid, ev)))

    source._poll_once()
    source._poll_once()  # Second poll — same updated_at, should be a no-op

    # Only 1 row in the DB (deduped)
    expected_event_id = _deterministic_event_id(
        thread_id, "github", "issue.polled",
        f"{anchor_id}:{updated_at}",
    )
    with _session_ctx(db_engine) as check_session:
        rows = check_session.execute(
            select(ThreadEvent).where(ThreadEvent.id == expected_event_id)
        ).scalars().all()
    assert len(rows) == 1  # deduped — only one row despite two polls

    # Filter to only events for this test's thread (other committed threads may exist)
    my_events = [tid for tid, ev in events_seen if tid == thread_id]
    # Handler must have been called exactly once — not on the second (duplicate) poll
    assert len(my_events) == 1, (
        f"Expected handler called once across two polls of unchanged thread, "
        f"got {len(my_events)}"
    )


def test_on_event_not_called_for_terminal_thread(db_engine):
    """on_event is NOT called for threads in terminal states."""
    anchor_id = _unique_anchor()
    with _session_ctx(db_engine) as seed_session:
        thread = crud.create_thread(
            anchor_type="github_issue",
            anchor_id=anchor_id,
            anchor_url=f"https://github.com/{anchor_id.replace('#', '/issues/')}",
            anchor_title="Done thread",
            session=seed_session,
        )
        state_machine.transition(thread.id, "noticed", seed_session)
        state_machine.transition(thread.id, "claimed", seed_session)
        state_machine.transition(thread.id, "executing", seed_session)
        state_machine.transition(thread.id, "pr_open", seed_session)
        state_machine.transition(thread.id, "done", seed_session)
        thread_id = thread.id  # capture inside session
        seed_session.commit()

    github = _make_github_mock()
    factory = _make_session_factory(db_engine)
    events_seen = []

    source = PollingEventSource(github, factory, poll_interval=120)
    source.on_event(lambda tid, ev: events_seen.append((tid, ev)))

    source._poll_once()

    # The done thread should NOT appear in events
    assert all(tid != thread_id for tid, _ in events_seen)


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
