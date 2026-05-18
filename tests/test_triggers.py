"""Tests for check_planned_done trigger (item #4).

All tests use real Postgres via the `session` fixture.
"""
from __future__ import annotations

import pytest

from guild import crud, state_machine
from guild.triggers import check_planned_done


def _make_thread(session, *, suffix: str = "", parent_id=None):
    return crud.create_thread(
        anchor_type="github_issue",
        anchor_id=f"owner/repo#999{suffix}",
        anchor_url=f"https://github.com/owner/repo/issues/999{suffix}",
        anchor_title=f"Thread {suffix}",
        session=session,
        parent_thread_id=parent_id,
    )


def test_planned_done_fires_when_all_children_terminal(session):
    """Parent transitions planned→done when every child is terminal."""
    parent = _make_thread(session, suffix="p")
    # Advance parent to planned
    state_machine.transition(parent.id, "noticed", session)
    state_machine.transition(parent.id, "claimed", session)
    state_machine.transition(parent.id, "executing", session)
    state_machine.transition(parent.id, "planned", session)
    session.flush()

    child1 = _make_thread(session, suffix="c1", parent_id=parent.id)
    state_machine.transition(child1.id, "noticed", session)
    state_machine.transition(child1.id, "claimed", session)
    state_machine.transition(child1.id, "executing", session)
    state_machine.transition(child1.id, "done", session)
    session.flush()

    child2 = _make_thread(session, suffix="c2", parent_id=parent.id)
    state_machine.transition(child2.id, "noticed", session)
    state_machine.transition(child2.id, "abandoned", session)
    session.flush()

    check_planned_done(session, parent.id)

    session.expire(parent)
    session.refresh(parent)
    assert parent.state == "done"


def test_planned_done_does_not_fire_if_child_active(session):
    """No transition if any child is still active."""
    parent = _make_thread(session, suffix="p2")
    state_machine.transition(parent.id, "noticed", session)
    state_machine.transition(parent.id, "claimed", session)
    state_machine.transition(parent.id, "executing", session)
    state_machine.transition(parent.id, "planned", session)
    session.flush()

    child1 = _make_thread(session, suffix="c3", parent_id=parent.id)
    state_machine.transition(child1.id, "noticed", session)
    state_machine.transition(child1.id, "claimed", session)
    state_machine.transition(child1.id, "executing", session)
    state_machine.transition(child1.id, "done", session)
    session.flush()

    child2 = _make_thread(session, suffix="c4", parent_id=parent.id)
    state_machine.transition(child2.id, "noticed", session)
    # child2 is still in 'noticed' — active
    session.flush()

    check_planned_done(session, parent.id)

    session.expire(parent)
    session.refresh(parent)
    assert parent.state == "planned"  # unchanged


def test_planned_done_noop_if_parent_not_planned(session):
    """No transition if parent is not in planned state."""
    parent = _make_thread(session, suffix="p3")
    state_machine.transition(parent.id, "noticed", session)
    state_machine.transition(parent.id, "claimed", session)
    state_machine.transition(parent.id, "executing", session)
    session.flush()
    # Parent is in 'executing', not 'planned'

    child = _make_thread(session, suffix="c5", parent_id=parent.id)
    state_machine.transition(child.id, "noticed", session)
    state_machine.transition(child.id, "claimed", session)
    state_machine.transition(child.id, "executing", session)
    state_machine.transition(child.id, "done", session)
    session.flush()

    check_planned_done(session, parent.id)

    session.expire(parent)
    session.refresh(parent)
    assert parent.state == "executing"  # unchanged


def test_planned_done_noop_if_no_parent(session):
    """check_planned_done(session, None) is a no-op."""
    # Should not raise
    check_planned_done(session, None)


def test_planned_done_noop_if_no_children(session):
    """No transition if parent has no children (nothing to aggregate)."""
    parent = _make_thread(session, suffix="p4")
    state_machine.transition(parent.id, "noticed", session)
    state_machine.transition(parent.id, "claimed", session)
    state_machine.transition(parent.id, "executing", session)
    state_machine.transition(parent.id, "planned", session)
    session.flush()

    check_planned_done(session, parent.id)

    session.expire(parent)
    session.refresh(parent)
    assert parent.state == "planned"  # unchanged — no children means no-op
