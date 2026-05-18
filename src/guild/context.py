"""Context assembly: builds the LLM prompt payload for a thread.

Assembles a structured context dict from Postgres that represents the
current state of a thread and its history.  The context is passed as
the user message to the decision layer.

Query design: single round-trip using selectinload on Thread relationships
so SQLAlchemy does not issue N+1 queries for events/notes/artifacts.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, selectinload

from guild.models import Thread

# Maximum items returned per collection to bound prompt size
_MAX_EVENTS = 50
_MAX_NOTES = 20
_MAX_ARTIFACTS = 10


def assemble_context(session: Session, thread_id: str) -> dict[str, Any]:
    """Return a structured context dict for *thread_id*.

    The dict shape is stable and used directly as the user message body
    sent to the Anthropic API.  Keys:

    - thread: core thread fields
    - events: recent GitHub events (capped at _MAX_EVENTS, newest last)
    - notes: worker observations/decisions (capped at _MAX_NOTES, newest last)
    - artifacts: produced artifacts like PRs (capped at _MAX_ARTIFACTS)

    Raises ValueError if the thread is not found.
    """
    thread = session.get(
        Thread,
        thread_id,
        options=[selectinload(Thread.events), selectinload(Thread.notes), selectinload(Thread.artifacts)],
    )
    if thread is None:
        raise ValueError(f"Thread {thread_id!r} not found")

    # Sort events by timestamp ascending so the narrative reads chronologically
    events_sorted = sorted(thread.events, key=lambda e: e.timestamp)
    events_tail = events_sorted[-_MAX_EVENTS:]

    # Notes newest-last so the most recent observation is at the bottom
    notes_sorted = sorted(thread.notes, key=lambda n: n.created_at)
    notes_tail = notes_sorted[-_MAX_NOTES:]

    # Artifacts newest-last
    artifacts_sorted = sorted(thread.artifacts, key=lambda a: a.created_at)
    artifacts_tail = artifacts_sorted[-_MAX_ARTIFACTS:]

    return {
        "thread": {
            "id": thread.id,
            "anchor_type": thread.anchor_type,
            "anchor_id": thread.anchor_id,
            "state": thread.state,
            "title": thread.anchor_title,
            "owner_id": thread.owner_id,
            "parent_thread_id": thread.parent_thread_id,
            "created_at": thread.created_at.isoformat() if thread.created_at else None,
            "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
        },
        "events": [
            {
                "id": e.id,
                "source": e.source,
                "type": e.type,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "payload": e.payload,
            }
            for e in events_tail
        ],
        "notes": [
            {
                "id": n.id,
                "note_type": n.note_type,
                "body": n.body,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes_tail
        ],
        "artifacts": [
            {
                "id": a.id,
                "artifact_type": a.type,
                "url": a.url,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in artifacts_tail
        ],
    }
