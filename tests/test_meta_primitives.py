"""Tests for ORM-backed meta primitives."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from guild.models import Thread, ThreadNote
from guild.primitives.meta import log_decision, update_thread_state, write_thread_note


def _make_thread(session: Session, state: str = "noticed") -> Thread:
    from ulid import ULID
    thread = Thread(
        id=str(ULID()),
        anchor_type="github_issue",
        anchor_id="repo/owner#1",
        anchor_url="https://github.com/repo/owner/issues/1",
        anchor_title="test thread",
        state=state,
    )
    session.add(thread)
    session.flush()
    return thread


def test_write_thread_note_success(session):
    thread = _make_thread(session)
    result = write_thread_note(session, thread.id, "status", "working on it")
    assert result.success
    session.flush()
    notes = session.query(ThreadNote).filter_by(thread_id=thread.id).all()
    assert len(notes) == 1
    assert notes[0].note_type == "status"
    assert notes[0].body == "working on it"


def test_write_thread_note_observation(session):
    """observation is a valid note_type (item #3)."""
    thread = _make_thread(session)
    result = write_thread_note(session, thread.id, "observation", "noticed something")
    assert result.success


def test_write_thread_note_invalid_type(session):
    thread = _make_thread(session)
    result = write_thread_note(session, thread.id, "bogus", "body")
    assert not result.success
    assert result.error.kind == "permanent"


def test_update_thread_state_success(session):
    thread = _make_thread(session, state="noticed")
    result = update_thread_state(session, thread.id, "claimed")
    assert result.success
    assert result.data["state"] == "claimed"
    session.flush()
    assert thread.state == "claimed"


def test_update_thread_state_illegal_transition(session):
    thread = _make_thread(session, state="noticed")
    result = update_thread_state(session, thread.id, "done")
    assert not result.success
    assert result.error.kind == "permanent"


def test_update_thread_state_not_found(session):
    result = update_thread_state(session, "nonexistent-id", "claimed")
    assert not result.success
    assert result.error.kind == "permanent"


def test_log_decision(session):
    import json
    thread = _make_thread(session)
    result = log_decision(session, thread.id, "this looks right", "open_pr", {"branch": "feat"})
    assert result.success
    session.flush()
    notes = session.query(ThreadNote).filter_by(thread_id=thread.id, note_type="decision").all()
    assert len(notes) == 1
    data = json.loads(notes[0].body)
    assert data["action"] == "open_pr"
    assert data["reasoning"] == "this looks right"
    assert data["params"] == {"branch": "feat"}
