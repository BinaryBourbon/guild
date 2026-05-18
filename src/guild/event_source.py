"""Event source abstraction and polling implementation.

PollingEventSource polls GitHub for active threads at a fixed interval,
normalizes new events, and deduplicates via INSERT ... ON CONFLICT DO NOTHING
(the UNIQUE constraint on thread_events.id handles this in write_event when
an explicit event_id is provided).
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Callable

from sqlalchemy.orm import Session

from guild import crud
from guild.github_client import GitHubClient
from guild.models import Thread

logger = logging.getLogger(__name__)

# Thread states that are "active" (should be polled for updates)
_ACTIVE_STATES = frozenset({"noticed", "claimed", "executing", "pr_open", "blocked", "planned"})


class EventSource(ABC):
    """Abstract base for event sources that drive the worker loop."""

    @abstractmethod
    def start(self) -> None:
        """Start the event source (blocking until stopped)."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Signal the event source to stop."""
        ...

    @abstractmethod
    def on_event(self, handler: Callable[[str, dict], None]) -> None:
        """Register a handler called with (thread_id, event_dict) for each new event."""
        ...


def _deterministic_event_id(thread_id: str, source: str, event_type: str, payload_key: str) -> str:
    """Stable ID for deduplication — same inputs always yield the same ID."""
    raw = f"{thread_id}:{source}:{event_type}:{payload_key}"
    return "evt_" + hashlib.sha256(raw.encode()).hexdigest()[:32]


class PollingEventSource(EventSource):
    """Polls GitHub for updates to active threads at a fixed interval.

    For each active thread, fetches the current GitHub issue/PR state via
    GitHubClient, normalizes the response into an event dict, and writes it
    with a deterministic event_id so the UNIQUE constraint on thread_events.id
    silently discards duplicates on re-poll (INSERT ON CONFLICT DO NOTHING).

    Dedup contract: write_event is called with event_id set to a hash of
    (thread_id, source, event_type, anchor_id+updated_at). If the DB already
    has that ID, the INSERT is silently ignored — no double-writes.
    """

    def __init__(
        self,
        github: GitHubClient,
        session_factory: Any,
        poll_interval: int = 120,
    ) -> None:
        self._github = github
        self._session_factory = session_factory
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._handler: Callable[[str, dict], None] | None = None

    def on_event(self, handler: Callable[[str, dict], None]) -> None:
        self._handler = handler

    def start(self) -> None:
        """Run the polling loop until stop() is called."""
        logger.info("PollingEventSource starting (interval=%ds)", self._poll_interval)
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.exception("Unhandled error in polling cycle; continuing")
            self._stop_event.wait(self._poll_interval)

    def stop(self) -> None:
        logger.info("PollingEventSource stopping")
        self._stop_event.set()

    def _poll_once(self) -> None:
        """Single poll cycle: iterate active threads, fetch GitHub state, write events."""
        with self._session_factory() as session:
            threads = (
                session.query(Thread)
                .filter(Thread.state.in_(_ACTIVE_STATES))
                .all()
            )

        for thread in threads:
            try:
                self._process_thread(thread)
            except Exception:
                logger.exception("Error processing thread %s; skipping", thread.id)

    def _process_thread(self, thread: Thread) -> None:
        """Fetch GitHub state for one thread and write any new events."""
        try:
            issue_data = self._fetch_github_state(thread)
        except Exception:
            logger.exception("Failed to fetch GitHub state for thread %s", thread.id)
            return

        # Build a deterministic event ID keyed on the issue's updated_at
        # so re-polling the same state is a no-op.
        updated_at = issue_data.get("updated_at", "")
        event_id = _deterministic_event_id(
            thread.id, "github", "issue.polled", f"{thread.anchor_id}:{updated_at}"
        )

        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)

        event_dict = {
            "id": event_id,
            "thread_id": thread.id,
            "source": "github",
            "type": "issue.polled",
            "timestamp": now.isoformat(),
            "payload": {
                "state": issue_data.get("state"),
                "title": issue_data.get("title"),
                "updated_at": updated_at,
                "labels": [lb["name"] for lb in issue_data.get("labels", [])],
                "number": issue_data.get("number"),
            },
        }

        try:
            with self._session_factory() as session:
                self._write_event_dedup(session, thread.id, event_id, now, event_dict["payload"])
                session.commit()
        except Exception:
            logger.exception("Failed to write event for thread %s", thread.id)
            return

        if self._handler is not None:
            try:
                self._handler(thread.id, event_dict)
            except Exception:
                logger.exception("Handler raised for thread %s", thread.id)

    def _fetch_github_state(self, thread: Thread) -> dict:
        """Fetch current issue/PR state from GitHub."""
        if thread.anchor_type == "github_issue":
            # anchor_id is "owner/repo#number" or just the issue number
            # We need the full repo path — stored in anchor_url, parse from it
            # anchor_url is typically https://github.com/owner/repo/issues/N
            parts = thread.anchor_url.rstrip("/").split("/")
            # [https:, '', github.com, owner, repo, issues, number]
            if len(parts) >= 7:
                owner, repo, number = parts[3], parts[4], parts[6]
                return self._github.get(f"/repos/{owner}/{repo}/issues/{number}")
        # Fallback: try anchor_id as "owner/repo#N"
        if "#" in thread.anchor_id:
            repo_part, number = thread.anchor_id.rsplit("#", 1)
            return self._github.get(f"/repos/{repo_part}/issues/{number}")
        raise ValueError(f"Cannot determine GitHub endpoint for thread {thread.id} anchor {thread.anchor_id!r}")

    def _write_event_dedup(self, session: Session, thread_id: str, event_id: str, now: Any, payload: dict) -> None:
        """Write event using deterministic ID; duplicate is silently ignored by DB constraint."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from guild.models import ThreadEvent

        stmt = pg_insert(ThreadEvent).values(
            id=event_id,
            thread_id=thread_id,
            source="github",
            type="issue.polled",
            actor_id=None,
            actor_name=None,
            timestamp=now,
            payload=payload,
        ).on_conflict_do_nothing(index_elements=["id"])
        session.execute(stmt)
        session.flush()
