"""Event source abstraction and polling implementation.

PollingEventSource polls GitHub for active threads at a fixed interval,
normalizes new events, and deduplicates via INSERT ... ON CONFLICT DO NOTHING
(the UNIQUE constraint on thread_events.id handles this in write_event when
an explicit event_id is provided).
"""
from __future__ import annotations

import datetime
import hashlib
import logging
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable

from sqlalchemy.dialects.postgresql import insert as pg_insert

from guild.github_client import GitHubClient
from guild.models import Thread, ThreadEvent

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

    Handler contract: on_event handler is only called when a genuinely new
    event is inserted (rowcount > 0). Re-polling unchanged GitHub state does
    not trigger the handler — and therefore does not call the Anthropic API.
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
        """Single poll cycle: iterate active threads, fetch GitHub state, write events.

        Thread data is snapshotted as plain dicts before the session closes
        to avoid DetachedInstanceError when processing outside the session.
        """
        with self._session_factory() as session:
            threads_snapshot = [
                {
                    "id": t.id,
                    "anchor_type": t.anchor_type,
                    "anchor_id": t.anchor_id,
                    "anchor_url": t.anchor_url,
                    "state": t.state,
                }
                for t in session.query(Thread).filter(Thread.state.in_(_ACTIVE_STATES)).all()
            ]

        for thread_data in threads_snapshot:
            try:
                self._process_thread(thread_data)
            except Exception:
                logger.exception("Error processing thread %s; skipping", thread_data["id"])

    def _process_thread(self, thread: dict) -> None:
        """Fetch GitHub state for one thread and write any new events."""
        try:
            issue_data = self._fetch_github_state(thread)
        except Exception:
            logger.exception("Failed to fetch GitHub state for thread %s", thread["id"])
            return

        # Build a deterministic event ID keyed on the issue's updated_at
        # so re-polling the same state is a no-op.
        updated_at = issue_data.get("updated_at", "")
        event_id = _deterministic_event_id(
            thread["id"], "github", "issue.polled",
            f"{thread['anchor_id']}:{updated_at}",
        )

        now = datetime.datetime.now(datetime.timezone.utc)

        payload = {
            "state": issue_data.get("state"),
            "title": issue_data.get("title"),
            "updated_at": updated_at,
            "labels": [lb["name"] for lb in issue_data.get("labels", [])],
            "number": issue_data.get("number"),
        }

        try:
            with self._session_factory() as session:
                stmt = pg_insert(ThreadEvent).values(
                    id=event_id,
                    thread_id=thread["id"],
                    source="github",
                    type="issue.polled",
                    actor_id=None,
                    actor_name=None,
                    timestamp=now,
                    payload=payload,
                ).on_conflict_do_nothing(index_elements=["id"])
                result = session.execute(stmt)
                session.commit()
        except Exception:
            logger.exception("Failed to write event for thread %s", thread["id"])
            return

        if result.rowcount > 0 and self._handler is not None:
            event_dict = {
                "id": event_id,
                "thread_id": thread["id"],
                "source": "github",
                "type": "issue.polled",
                "timestamp": now.isoformat(),
                "payload": payload,
            }
            try:
                self._handler(thread["id"], event_dict)
            except Exception:
                logger.exception("Handler raised for thread %s", thread["id"])

    def _fetch_github_state(self, thread: dict) -> dict:
        """Fetch current issue/PR state from GitHub."""
        anchor_url = thread.get("anchor_url", "")
        anchor_id = thread.get("anchor_id", "")

        if thread["anchor_type"] == "github_issue":
            # anchor_url: https://github.com/owner/repo/issues/N
            parts = anchor_url.rstrip("/").split("/")
            if len(parts) >= 7:
                owner, repo, number = parts[3], parts[4], parts[6]
                return self._github.get(f"/repos/{owner}/{repo}/issues/{number}")

        # Fallback: try anchor_id as "owner/repo#N"
        if "#" in anchor_id:
            repo_part, number = anchor_id.rsplit("#", 1)
            return self._github.get(f"/repos/{repo_part}/issues/{number}")

        raise ValueError(
            f"Cannot determine GitHub endpoint for thread {thread['id']} "
            f"anchor_type={thread['anchor_type']!r} anchor_id={anchor_id!r}"
        )
