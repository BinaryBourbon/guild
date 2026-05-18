"""Meta primitives: ORM-backed thread operations.

These primitives operate on the local database rather than GitHub.
They accept a SQLAlchemy Session and call flush() — never commit().
The transaction boundary belongs to the caller (polling loop).
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from guild import crud, state_machine
from guild.models import Thread
from guild.primitives import ActionResult, PrimitiveError


def write_thread_note(
    session: Session,
    thread_id: str,
    note_type: str,
    body: str,
) -> ActionResult:
    """Append a note to *thread_id*.

    note_type must be one of: decision, status, error, observation.
    crud.write_note() flushes the session.
    """
    valid = {"decision", "status", "error", "observation"}
    if note_type not in valid:
        return ActionResult(
            success=False,
            error=PrimitiveError("permanent", f"invalid note_type {note_type!r}; must be one of {valid}"),
        )
    try:
        note = crud.write_note(session, thread_id=thread_id, note_type=note_type, body=body)
        return ActionResult(success=True, data={"note_id": note.id})
    except Exception as exc:  # noqa: BLE001
        return ActionResult(success=False, error=PrimitiveError("transient", str(exc)))


def update_thread_state(
    session: Session,
    thread_id: str,
    to_state: str,
) -> ActionResult:
    """Transition *thread_id* to *to_state* with row-level locking.

    Flushes after transition so the state change is visible within the
    current transaction without committing.
    """
    try:
        thread = state_machine.transition(thread_id, to_state, session)
        session.flush()
        return ActionResult(success=True, data={"state": thread.state})
    except state_machine.IllegalTransition as exc:
        return ActionResult(success=False, error=PrimitiveError("permanent", str(exc)))
    except ValueError as exc:
        return ActionResult(success=False, error=PrimitiveError("permanent", str(exc)))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(success=False, error=PrimitiveError("transient", str(exc)))


def log_decision(
    session: Session,
    thread_id: str,
    reasoning: str,
    action: str,
    params: dict,
) -> ActionResult:
    """Record a decision made by the decision layer as a thread note.

    Stored as JSON so the full decision context is queryable.
    """
    payload = json.dumps({"reasoning": reasoning, "action": action, "params": params})
    return write_thread_note(session, thread_id, "decision", payload)
