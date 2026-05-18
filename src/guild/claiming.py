"""Claiming loop: polls GitHub for issues labelled guild-claim and upserts threads.

Conflict-avoidance filters (all required, per item #5):
1. Skip if assigned to a human (issue["assignee"] is not None)
2. Skip if an active thread (claimed/executing/pr_open/blocked/planned) exists
   for this anchor — another worker is on it
3. Skip if this worker previously abandoned the thread (thread.state == 'abandoned'
   AND thread.owner_id == config.worker_id) — item #5
4. Skip if thread is in a terminal state other than the re-claim path — avoids
   wasting Anthropic API calls on done/abandoned threads (slice 5 review item #1)
"""
from __future__ import annotations

import datetime
import logging
import threading
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from guild import crud, state_machine
from guild.config import Config
from guild.github_client import GitHubClient
from guild.models import Thread
from guild.state_machine import TERMINAL_STATES

logger = logging.getLogger(__name__)

# States that mean "another worker has this"
_ACTIVE_WORKER_STATES = frozenset({"claimed", "executing", "pr_open", "blocked", "planned"})


class ClaimingLoop:
    """Periodically checks GitHub for claimable issues and upserts threads.

    Issues that pass all three conflict filters get a Thread upserted and
    transitioned to 'noticed', then the on_event handler is called so the
    decision layer can immediately act.
    """

    def __init__(
        self,
        github: GitHubClient,
        session_factory: Any,
        config: Config,
        on_event_handler: Callable[[str, dict], None],
    ) -> None:
        self._github = github
        self._session_factory = session_factory
        self._config = config
        self._handler = on_event_handler
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Run the claiming loop until stop() is called."""
        logger.info("ClaimingLoop starting (interval=%ds)", self._config.claim_interval)
        while not self._stop_event.is_set():
            try:
                self._claim_once()
            except Exception:
                logger.exception("Unhandled error in claiming cycle; continuing")
            self._stop_event.wait(self._config.claim_interval)

    def stop(self) -> None:
        logger.info("ClaimingLoop stopping")
        self._stop_event.set()

    def _claim_once(self) -> None:
        """Single claim cycle: fetch labelled issues, apply filters, upsert threads."""
        owner, repo = self._config.guild_repo.split("/", 1)
        try:
            issues = self._github.get(
                f"/repos/{owner}/{repo}/issues",
                params={"labels": "guild-claim", "state": "open", "per_page": 100},
            )
        except Exception:
            logger.exception("Failed to fetch issues from GitHub")
            return

        for issue in issues:
            try:
                self._process_issue(issue, owner, repo)
            except Exception:
                logger.exception("Error processing issue #%s; skipping", issue.get("number"))

    def _process_issue(self, issue: dict, owner: str, repo: str) -> None:
        """Apply conflict filters and upsert a thread for the issue if it passes."""
        # Filter 1: skip if assigned to a human
        if issue.get("assignee") is not None:
            logger.debug("Issue #%s has a human assignee; skipping", issue["number"])
            return

        anchor_type = "github_issue"
        anchor_id = f"{owner}/{repo}#{issue['number']}"
        anchor_url = issue["html_url"]
        anchor_title = issue["title"]

        with self._session_factory() as session:
            existing = self._find_thread(session, anchor_type, anchor_id)

            if existing is not None:
                # Filter 2: active thread from any worker — someone else is on it
                if existing.state in _ACTIVE_WORKER_STATES:
                    logger.debug(
                        "Issue #%s has active thread %s (state=%s); skipping",
                        issue["number"], existing.id, existing.state,
                    )
                    return

                # Filter 3 (item #5): this worker previously abandoned it — don't retry
                if (
                    existing.state == "abandoned"
                    and existing.owner_id == self._config.worker_id
                ):
                    logger.debug(
                        "Issue #%s was previously abandoned by this worker; skipping",
                        issue["number"],
                    )
                    return

                # Filter 4 (slice 5 review item #1): skip terminal-state threads that
                # are not the re-claim path.  After filter 3, any 'abandoned' thread
                # that reaches here is owned by a DIFFERENT worker — that is the
                # legitimate re-claim path and must stay live.  All other terminal
                # states (e.g. 'done') have no valid transition left; firing on_event
                # would only waste an Anthropic API call and raise IllegalTransition.
                if existing.state in TERMINAL_STATES and existing.state != "abandoned":
                    logger.debug(
                        "Issue #%s thread %s is in terminal state %r; skipping",
                        issue["number"], existing.id, existing.state,
                    )
                    return

            # Create thread if it doesn't exist yet
            if existing is None:
                thread = crud.create_thread(
                    anchor_type=anchor_type,
                    anchor_id=anchor_id,
                    anchor_url=anchor_url,
                    anchor_title=anchor_title,
                    session=session,
                )
                thread.owner_id = self._config.worker_id
                thread.owner_type = "worker"
                session.flush()
            else:
                thread = existing

            # Transition unnoticed → noticed if possible.
            # Skip if thread is already past unnoticed or in a terminal state
            # (e.g., abandoned by a different worker — we just fire the event).
            if thread.state == "unnoticed":
                state_machine.transition(thread.id, "noticed", session)
                session.flush()

            thread_id = thread.id
            session.commit()

        # Fire event so the decision layer can act immediately
        event_dict = {
            "thread_id": thread_id,
            "source": "claiming",
            "type": "issue.noticed",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "payload": {
                "number": issue["number"],
                "title": anchor_title,
                "url": anchor_url,
            },
        }
        if self._handler is not None:
            try:
                self._handler(thread_id, event_dict)
            except Exception:
                logger.exception("Handler raised for thread %s", thread_id)

    def _find_thread(self, session: Session, anchor_type: str, anchor_id: str) -> Thread | None:
        stmt = select(Thread).where(
            Thread.anchor_type == anchor_type,
            Thread.anchor_id == anchor_id,
        )
        return session.execute(stmt).scalar_one_or_none()
