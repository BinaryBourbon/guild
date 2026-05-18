"""Tests for context assembly."""
from __future__ import annotations

import datetime

import pytest
from ulid import ULID
from sqlalchemy.orm import Session

from guild.context import assemble_context
from guild.models import Thread, ThreadArtifact, ThreadEvent, ThreadNote


def _ts(offset_seconds: int = 0) -> datetime.datetime:
    base = datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    return base + datetime.timedelta(seconds=offset_seconds)


def _make_thread(session: Session, **kwargs) -> Thread:
    thread = Thread(
        id=str(ULID()),
        anchor_type="github_issue",
        anchor_id="owner/repo#42",
        anchor_url="https://github.com/repo/owner/issues/42",
        anchor_title="test",
        state="noticed",
        **kwargs,
    )
    session.add(thread)
    session.flush()
    return thread


def test_assemble_context_empty_thread(session):
    thread = _make_thread(session)
    ctx = assemble_context(session, thread.id)

    assert ctx["thread"]["id"] == thread.id
    assert ctx["thread"]["state"] == "noticed"
    assert ctx["thread"]["anchor_type"] == "github_issue"
    assert ctx["events"] == []
    assert ctx["notes"] == []
    assert ctx["artifacts"] == []


def test_assemble_context_not_found(session):
    with pytest.raises(ValueError, match="not found"):
        assemble_context(session, "nonexistent-id")


def test_assemble_context_with_events(session):
    thread = _make_thread(session)
    # Add events out of order; context should sort by timestamp
    e2 = ThreadEvent(
        id=str(ULID()), thread_id=thread.id, source="github",
        type="issue.labeled", timestamp=_ts(10), payload={"label": "bug"},
    )
    e1 = ThreadEvent(
        id=str(ULID()), thread_id=thread.id, source="github",
        type="issue.opened", timestamp=_ts(0), payload={"title": "fix me"},
    )
    session.add_all([e2, e1])
    session.flush()

    ctx = assemble_context(session, thread.id)
    assert len(ctx["events"]) == 2
    # Sorted chronologically: opened before labeled
    assert ctx["events"][0]["type"] == "issue.opened"
    assert ctx["events"][1]["type"] == "issue.labeled"


def test_assemble_context_with_notes(session):
    thread = _make_thread(session)
    n = ThreadNote(
        id=str(ULID()), thread_id=thread.id,
        author_id="worker",
        note_type="status", body="started working",
    )
    session.add(n)
    session.flush()

    ctx = assemble_context(session, thread.id)
    assert len(ctx["notes"]) == 1
    assert ctx["notes"][0]["note_type"] == "status"
    assert ctx["notes"][0]["body"] == "started working"


def test_assemble_context_with_artifacts(session):
    thread = _make_thread(session)
    a = ThreadArtifact(
        id=str(ULID()), thread_id=thread.id,
        type="pull_request", external_id="1", url="https://github.com/o/r/pull/1",
    )
    session.add(a)
    session.flush()

    ctx = assemble_context(session, thread.id)
    assert len(ctx["artifacts"]) == 1
    assert ctx["artifacts"][0]["artifact_type"] == "pull_request"
    assert ctx["artifacts"][0]["url"] == "https://github.com/o/r/pull/1"


def test_assemble_context_event_cap(session):
    """Events are capped at _MAX_EVENTS (20); oldest are dropped."""
    from guild.context import _MAX_EVENTS
    thread = _make_thread(session)
    for i in range(_MAX_EVENTS + 5):  # seed 25 events
        session.add(ThreadEvent(
            id=str(ULID()), thread_id=thread.id, source="github",
            type="push", timestamp=_ts(i), payload={"n": i},
        ))
    session.flush()

    ctx = assemble_context(session, thread.id)
    assert len(ctx["events"]) == _MAX_EVENTS
    # Should have the newest events (tail)
    payloads = [e["payload"]["n"] for e in ctx["events"]]
    assert payloads == list(range(5, _MAX_EVENTS + 5))


def test_assemble_context_timestamps_serialized(session):
    """Timestamps are ISO 8601 strings in the context dict."""
    thread = _make_thread(session)
    session.add(ThreadEvent(
        id=str(ULID()), thread_id=thread.id, source="internal",
        type="state.transition", timestamp=_ts(0), payload={},
    ))
    session.flush()

    ctx = assemble_context(session, thread.id)
    ts = ctx["events"][0]["timestamp"]
    assert isinstance(ts, str)
    # Parseable as ISO datetime
    parsed = datetime.datetime.fromisoformat(ts)
    assert parsed == _ts(0)


# ---------------------------------------------------------------------------
# New tests for fix items 10-12
# ---------------------------------------------------------------------------

def test_assemble_context_includes_current_event(session):
    """Fix #10: current_event must appear in the assembled context packet."""
    thread = _make_thread(session)
    event = {"source": "github", "type": "issue.commented", "payload": {"body": "hello"}}

    ctx = assemble_context(session, thread.id, current_event=event)

    assert "current_event" in ctx
    assert ctx["current_event"] == event


def test_assemble_context_event_cap_25_seeds(session):
    """Fix #11: with 25 seeded events, at most 20 appear in 'events'."""
    from guild.context import _MAX_EVENTS
    assert _MAX_EVENTS == 20, "_MAX_EVENTS must be 20 per spec"

    thread = _make_thread(session)
    for i in range(25):
        session.add(ThreadEvent(
            id=str(ULID()), thread_id=thread.id, source="github",
            type="push", timestamp=_ts(i), payload={"n": i},
        ))
    session.flush()

    ctx = assemble_context(session, thread.id)
    assert len(ctx["events"]) <= 20


def test_assemble_context_notes_unbounded(session):
    """Fix #12: all notes are returned regardless of count — no cap."""
    thread = _make_thread(session)
    for i in range(25):
        session.add(ThreadNote(
            id=str(ULID()), thread_id=thread.id,
            author_id="worker",
            note_type="status",
            body=f"note {i}",
        ))
    session.flush()

    ctx = assemble_context(session, thread.id)
    assert len(ctx["notes"]) == 25
