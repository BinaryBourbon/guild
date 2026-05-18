"""ORM model round-trip tests."""
import datetime

from guild.crud import create_thread, write_artifact, write_event, write_note
from guild.models import Thread, ThreadArtifact, ThreadEvent, ThreadNote

_TS = datetime.datetime.now(datetime.timezone.utc)


def test_thread_create_and_read(session):
    t = create_thread("github_issue", "owner/repo#1", "https://x", "Fix it", session)
    fetched = session.get(Thread, t.id)
    assert fetched is not None
    assert fetched.anchor_type == "github_issue"
    assert fetched.state == "unnoticed"


def test_thread_event_round_trip(session):
    t = create_thread("github_issue", "owner/repo#2", "https://x", "Evt test", session)
    ev = write_event(t.id, "github", "issue.created", _TS, session,
                     payload={"action": "opened"})
    fetched = session.get(ThreadEvent, ev.id)
    assert fetched.type == "issue.created"
    assert fetched.payload == {"action": "opened"}


def test_thread_artifact_round_trip(session):
    t = create_thread("github_issue", "owner/repo#3", "https://x", "Art test", session)
    art = write_artifact(t.id, "pull_request", "42", session,
                         url="https://github.com/owner/repo/pull/42",
                         title="Fix the thing", state="open")
    fetched = session.get(ThreadArtifact, art.id)
    assert fetched.type == "pull_request"
    assert fetched.state == "open"


def test_thread_note_round_trip(session):
    t = create_thread("github_issue", "owner/repo#4", "https://x", "Note test", session)
    note = write_note(t.id, "worker-0", "decision", "Chose approach X.", session)
    fetched = session.get(ThreadNote, note.id)
    assert fetched.note_type == "decision"
    assert fetched.body == "Chose approach X."


def test_parent_child_thread(session):
    parent = create_thread("github_issue", "owner/repo#5", "https://x", "Parent", session)
    child = create_thread("github_issue", "owner/repo#6", "https://x", "Child", session,
                          parent_thread_id=parent.id)
    assert child.parent_thread_id == parent.id


def test_thread_relationships_start_empty(session):
    t = create_thread("github_issue", "owner/repo#7", "https://x", "Empty", session)
    session.flush()
    session.expire(t)  # force reload
    assert t.events == []
    assert t.artifacts == []
    assert t.notes == []


def test_thread_events_relationship(session):
    t = create_thread("github_issue", "owner/repo#8", "https://x", "Rel test", session)
    write_event(t.id, "github", "issue.created", _TS, session)
    write_event(t.id, "github", "issue.assigned", _TS, session)
    session.flush()
    session.expire(t)
    assert len(t.events) == 2
