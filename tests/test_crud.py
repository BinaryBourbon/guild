"""Round-trip tests for guild.crud."""
import datetime

from guild.crud import (
    create_thread, get_thread, write_artifact, write_event, write_note,
)

_TS = datetime.datetime.now(datetime.timezone.utc)


def test_create_and_get_thread(session):
    t = create_thread("github_issue", "owner/repo#10", "https://x", "CRUD test", session)
    fetched = get_thread(t.id, session)
    assert fetched is not None
    assert fetched.anchor_id == "owner/repo#10"
    assert fetched.state == "unnoticed"


def test_get_thread_returns_none_for_missing(session):
    assert get_thread("nonexistent-id", session) is None


def test_write_event(session):
    t = create_thread("github_issue", "owner/repo#11", "https://x", "Evt", session)
    ev = write_event(t.id, "github", "issue.labeled", _TS, session,
                     payload={"label": "guild-claim"})
    assert ev.id is not None
    assert ev.type == "issue.labeled"
    assert ev.payload == {"label": "guild-claim"}


def test_write_event_with_explicit_id(session):
    t = create_thread("github_issue", "owner/repo#12", "https://x", "Evt id", session)
    ev = write_event(t.id, "github", "issue.created", _TS, session, event_id="explicit-id-1")
    assert ev.id == "explicit-id-1"


def test_write_note(session):
    t = create_thread("github_issue", "owner/repo#13", "https://x", "Note", session)
    note = write_note(t.id, "worker-0", "decision", "Chose approach X.", session)
    assert note.id is not None
    assert note.note_type == "decision"


def test_write_artifact(session):
    t = create_thread("github_issue", "owner/repo#14", "https://x", "Art", session)
    art = write_artifact(t.id, "pull_request", "99", session,
                         url="https://github.com/owner/repo/pull/99",
                         title="My PR", state="open")
    assert art.id is not None
    assert art.external_id == "99"
    assert art.state == "open"


def test_create_thread_with_parent(session):
    parent = create_thread("github_issue", "owner/repo#15", "https://x", "Parent", session)
    child = create_thread("github_issue", "owner/repo#16", "https://x", "Child", session,
                          parent_thread_id=parent.id)
    assert child.parent_thread_id == parent.id
