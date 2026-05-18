"""Post-transition triggers: side effects that fire after state changes.

check_planned_done (item #4):
  Called after any child thread transitions to a terminal state.
  If the parent thread is in 'planned' state and ALL sibling threads
  (children of the same parent) are in a terminal state ('done' or 'abandoned'),
  the parent is automatically transitioned to 'done'.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from guild import state_machine
from guild.models import Thread
from guild.state_machine import TERMINAL_STATES

logger = logging.getLogger(__name__)


def check_planned_done(session: Session, thread_id: str | None) -> None:
    """If thread_id's parent is in 'planned' state and all siblings are terminal,
    transition parent to 'done'.

    This is a no-op if:
    - thread_id is None (thread has no parent)
    - The parent thread is not in 'planned' state
    - Any sibling thread is not yet in a terminal state
    """
    if thread_id is None:
        return

    parent = session.get(Thread, thread_id)
    if parent is None:
        logger.warning("check_planned_done called with unknown thread_id %r", thread_id)
        return

    if parent.state != "planned":
        return

    # Check that all children are terminal
    children = session.execute(
        select(Thread).where(Thread.parent_thread_id == thread_id)
    ).scalars().all()

    if not children:
        # No children — nothing to check
        return

    all_terminal = all(child.state in TERMINAL_STATES for child in children)
    if not all_terminal:
        return

    logger.info(
        "All children of planned thread %s are terminal — transitioning to done", thread_id
    )
    state_machine.transition(thread_id, "done", session)
    session.flush()
