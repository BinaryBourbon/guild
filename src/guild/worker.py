"""Worker event handler: assemble context, decide, dispatch action.

run_event is the on_event handler body. It:
1. Assembles context for the thread
2. Asks the decision layer what to do next
3. Dispatches the chosen action via run_primitive
4. After update_thread_state actions, calls check_planned_done for the parent
5. Commits on success; rolls back and logs on any exception

The transaction boundary is per-event: one commit per successful run_event
call. Exceptions do not crash the loop — they are logged and the session
is rolled back so subsequent events can be processed.
"""
from __future__ import annotations

import logging
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from guild.context import assemble_context
from guild.decision import decide
from guild.github_client import GitHubClient
from guild.primitives import run_primitive
from guild.triggers import check_planned_done
from guild import crud

logger = logging.getLogger(__name__)


def _get_primitive_fn(action: str):
    """Return the callable for *action*, or None if unknown."""
    # Import here to avoid circular deps and keep mapping close to usage
    from guild.primitives.code import (
        create_branch, commit_and_push, open_pull_request, push_to_branch,
    )
    from guild.primitives.communication import comment_on_issue, comment_on_pr
    from guild.primitives.meta import update_thread_state, write_thread_note, log_decision
    from guild.primitives.work import assign_to_self, add_label

    action_map = {
        "create_branch": create_branch,
        "commit_and_push": commit_and_push,
        "open_pull_request": open_pull_request,
        "push_to_branch": push_to_branch,
        "comment_on_issue": comment_on_issue,
        "comment_on_pr": comment_on_pr,
        "update_thread_state": update_thread_state,
        "write_thread_note": write_thread_note,
        "log_decision": log_decision,
        "assign_to_self": assign_to_self,
        "add_label": add_label,
    }
    return action_map.get(action)


_GITHUB_ACTIONS = frozenset({
    "create_branch", "commit_and_push", "open_pull_request", "push_to_branch",
    "comment_on_issue", "comment_on_pr", "assign_to_self", "add_label",
})

_SESSION_ACTIONS = frozenset({
    "update_thread_state", "write_thread_note", "log_decision",
})


def run_event(
    session: Session,
    thread_id: str,
    event: dict,
    github_client: GitHubClient,
    anthropic_client: anthropic.Anthropic,
) -> None:
    """Process one event for a thread.

    Assembles context, asks the decision layer for the next action, dispatches
    the primitive, and commits. On any exception, rolls back and logs — does
    NOT re-raise so the calling loop continues.
    """
    try:
        context = assemble_context(session, thread_id)
        action, params = decide(
            context,
            anthropic_client=anthropic_client,
            session=session,
            thread_id=thread_id,
        )

        if action == "wait":
            logger.info("Thread %s: decision=wait, no action taken", thread_id)
            session.commit()
            return

        if action == "abandon":
            from guild.state_machine import transition
            transition(thread_id, "abandoned", session)
            session.commit()
            logger.info("Thread %s abandoned", thread_id)
            return

        if action == "claim_thread":
            from guild.state_machine import transition
            transition(thread_id, "claimed", session)
            session.flush()
            session.commit()
            logger.info("Thread %s claimed", thread_id)
            return

        primitive_fn = _get_primitive_fn(action)
        if primitive_fn is None:
            logger.error("Unknown action %r for thread %s; skipping", action, thread_id)
            session.rollback()
            return

        # Build full params: inject session for meta actions, client for GitHub actions
        full_params = dict(params)
        if action in _SESSION_ACTIONS:
            full_params.setdefault("session", session)
        if action in _GITHUB_ACTIONS:
            # Primitives use 'client' as their first positional param name
            full_params.setdefault("client", github_client)

        result = run_primitive(primitive_fn, full_params)

        if not result.success:
            logger.warning(
                "Primitive %r failed for thread %s: %s",
                action, thread_id,
                result.error.message if result.error else "unknown",
            )

        # After update_thread_state, check if parent can transition to done
        if action == "update_thread_state" and result.success:
            thread = crud.get_thread(thread_id, session)
            if thread is not None and thread.parent_thread_id is not None:
                check_planned_done(session, thread.parent_thread_id)

        session.commit()
        logger.info("Thread %s: action=%s success=%s", thread_id, action, result.success)

    except Exception:
        logger.exception("Exception handling event for thread %s; rolling back", thread_id)
        try:
            session.rollback()
        except Exception:
            logger.exception("Rollback failed for thread %s", thread_id)
