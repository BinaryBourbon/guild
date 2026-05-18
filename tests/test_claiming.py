"""Tests for ClaimingLoop conflict-avoidance filters and happy path.

All tests use real Postgres via the `session` fixture.
GitHub calls are mocked via a fake GitHubClient.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

from guild import crud, state_machine
from guild.claiming import ClaimingLoop
from guild.config import Config


def _make_config(
    worker_id: str = "worker-test",
    guild_repo: str = "owner/repo",
) -> Config:
    return Config(
        database_url="postgresql+psycopg://guild:guild@localhost:5432/guild_test",
        github_token="tok",
        anthropic_api_key="sk",
        port=8000,
        worker_id=worker_id,
        guild_repo=guild_repo,
        poll_interval=120,
        claim_interval=300,
    )


def _make_issue(number: int = 1, assignee=None, title: str = "Test issue") -> dict:
    return {
        "number": number,
        "title": title,
        "html_url": f"https://github.com/owner/repo/issues/{number}",
        "assignee": assignee,
        "labels": [{"name": "guild-claim"}],
    }


def _make_session_factory(session):
    """Return a session factory that yields the provided session."""
    @contextmanager
    def factory():
        yield session
    return factory


def _make_loop(session, worker_id="worker-test", guild_repo="owner/repo"):
    config = _make_config(worker_id=worker_id, guild_repo=guild_repo)
    github = MagicMock()
    github.get.return_value = [_make_issue()]
    events = []
    loop = ClaimingLoop(
        github=github,
        session_factory=_make_session_factory(session),
        config=config,
        on_event_handler=lambda tid, ev: events.append((tid, ev)),
    )
    return loop, github, events


def test_filter1_skips_if_human_assignee(session):
    """Filter 1: skip issues assigned to a human."""
    loop, github, events = _make_loop(session)
    issue = _make_issue(assignee={"login": "some-human", "type": "User"})
    github.get.return_value = [issue]

    loop._claim_once()

    assert events == []


def test_filter2_skips_if_active_thread_exists(session):
    """Filter 2: skip if an active thread (executing, etc.) exists for this anchor."""
    # Seed: create a thread that is in 'executing' state
    thread = crud.create_thread(
        anchor_type="github_issue",
        anchor_id="owner/repo#1",
        anchor_url="https://github.com/owner/repo/issues/1",
        anchor_title="Test issue",
        session=session,
    )
    state_machine.transition(thread.id, "noticed", session)
    state_machine.transition(thread.id, "claimed", session)
    state_machine.transition(thread.id, "executing", session)
    session.flush()

    loop, github, events = _make_loop(session)
    loop._claim_once()

    assert events == []


def test_filter3_skips_if_this_worker_abandoned(session):
    """Filter 3 (item #5): skip if this worker previously abandoned the thread."""
    worker_id = "worker-abc"
    thread = crud.create_thread(
        anchor_type="github_issue",
        anchor_id="owner/repo#1",
        anchor_url="https://github.com/owner/repo/issues/1",
        anchor_title="Test",
        session=session,
    )
    state_machine.transition(thread.id, "noticed", session)
    # Abandon from noticed
    state_machine.transition(thread.id, "abandoned", session)
    thread.owner_id = worker_id
    session.flush()

    loop, github, events = _make_loop(session, worker_id=worker_id)
    loop._claim_once()

    assert events == []


def test_filter3_does_not_skip_if_different_worker_abandoned(session):
    """Filter 3: another worker's abandoned thread should NOT block us."""
    thread = crud.create_thread(
        anchor_type="github_issue",
        anchor_id="owner/repo#1",
        anchor_url="https://github.com/owner/repo/issues/1",
        anchor_title="Test",
        session=session,
    )
    state_machine.transition(thread.id, "noticed", session)
    state_machine.transition(thread.id, "abandoned", session)
    thread.owner_id = "some-other-worker"
    session.flush()

    loop, github, events = _make_loop(session, worker_id="our-worker")
    loop._claim_once()

    # Should fire an event (thread exists but is abandoned by a different worker)
    assert len(events) == 1


def test_successful_claim_fires_event(session):
    """Happy path: new issue creates thread and fires event."""
    loop, github, events = _make_loop(session)

    loop._claim_once()

    assert len(events) == 1
    thread_id, event = events[0]
    assert event["type"] == "issue.noticed"
    assert event["payload"]["number"] == 1


def test_unnoticed_to_noticed_transition(session):
    """New thread starts unnoticed and gets transitioned to noticed."""
    loop, github, events = _make_loop(session)
    loop._claim_once()

    assert len(events) == 1
    thread_id, _ = events[0]

    from guild.crud import get_thread
    thread = get_thread(thread_id, session)
    # After claiming, state should be 'noticed'
    assert thread.state == "noticed"
