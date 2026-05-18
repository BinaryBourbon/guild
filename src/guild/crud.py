"""Basic CRUD operations for the Guild thread model.

All functions accept a Session and do NOT commit.  Callers own the
transaction boundary.  Use session.flush() if you need DB-generated values
(e.g. server_default timestamps) visible before committing.

Note: write_event does not deduplicate — ON CONFLICT DO NOTHING is the
polling loop’s responsibility (Slice 5 / g2-slice-5-e2e).
"""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy.orm import Session
from ulid import ULID

from guild.models import Thread, ThreadArtifact, ThreadEvent, ThreadNote


def create_thread(
    anchor_type: str,
    anchor_id: str,
    anchor_url: str,
    anchor_title: str,
    session: Session,
    *,
    parent_thread_id: Optional[str] = None,
) -> Thread:
    thread = Thread(
        id=str(ULID()),
        anchor_type=anchor_type,
        anchor_id=anchor_id,
        anchor_url=anchor_url,
        anchor_title=anchor_title,
        parent_thread_id=parent_thread_id,
    )
    session.add(thread)
    session.flush()
    return thread


def get_thread(thread_id: str, session: Session) -> Optional[Thread]:
    return session.get(Thread, thread_id)


def write_event(
    thread_id: str,
    source: str,
    event_type: str,
    timestamp: datetime.datetime,
    session: Session,
    *,
    actor_id: Optional[str] = None,
    actor_name: Optional[str] = None,
    payload: Optional[dict] = None,
    event_id: Optional[str] = None,
) -> ThreadEvent:
    event = ThreadEvent(
        id=event_id or str(ULID()),
        thread_id=thread_id,
        source=source,
        type=event_type,
        actor_id=actor_id,
        actor_name=actor_name,
        timestamp=timestamp,
        payload=payload or {},
    )
    session.add(event)
    session.flush()
    return event


def write_note(
    thread_id: str,
    author_id: str,
    note_type: str,
    body: str,
    session: Session,
) -> ThreadNote:
    note = ThreadNote(
        id=str(ULID()),
        thread_id=thread_id,
        author_id=author_id,
        note_type=note_type,
        body=body,
    )
    session.add(note)
    session.flush()
    return note


def write_artifact(
    thread_id: str,
    artifact_type: str,
    external_id: str,
    session: Session,
    *,
    url: Optional[str] = None,
    title: Optional[str] = None,
    state: Optional[str] = None,
) -> ThreadArtifact:
    artifact = ThreadArtifact(
        id=str(ULID()),
        thread_id=thread_id,
        type=artifact_type,
        external_id=external_id,
        url=url,
        title=title,
        state=state,
    )
    session.add(artifact)
    session.flush()
    return artifact
