"""State machine for Guild threads.

TRANSITIONS defines the legal moves between active states.  'abandoned' is
not listed in any transition set — it is universally reachable from any
active state and is handled as a special case in transition().

Callers own the transaction boundary: transition() flushes but does NOT
commit.  Commit or rollback is the caller’s responsibility.
"""
from __future__ import annotations

import datetime

from sqlalchemy.orm import Session
from ulid import ULID

from guild.models import Thread, ThreadEvent

# Legal transitions between active states per engineering plan §2.
# 'abandoned' is intentionally absent from every frozenset — transition()
# allows it unconditionally from any non-terminal state via the special case.
TRANSITIONS: dict[str, frozenset[str]] = {
    "unnoticed": frozenset({"noticed"}),
    "noticed":   frozenset({"claimed", "unnoticed"}),
    "claimed":   frozenset({"executing"}),
    "executing": frozenset({"pr_open", "blocked", "planned"}),
    "pr_open":   frozenset({"executing", "done"}),
    "blocked":   frozenset({"executing"}),
    "planned":   frozenset({"done"}),
}

TERMINAL_STATES: frozenset[str] = frozenset({"done", "abandoned"})


class IllegalTransition(Exception):
    """Raised when a requested state transition is not permitted."""


def transition(thread_id: str, to_state: str, session: Session) -> Thread:
    """Transition a thread to a new state under a row-level lock.

    Issues SELECT ... FOR UPDATE on the thread row.  The lock is held for
    the duration of the caller’s transaction, preventing concurrent workers
    from racing on the same thread.

    'abandoned' is accepted from any active (non-terminal) state regardless
    of what TRANSITIONS specifies.  All other transitions are validated
    against TRANSITIONS.

    Writes a ``state.transition`` event to thread_events in the same session.

    Raises:
        ValueError: thread_id not found.
        IllegalTransition: transition not permitted from current state.
    """
    thread = session.get(Thread, thread_id, with_for_update=True)
    if thread is None:
        raise ValueError(f"Thread {thread_id!r} not found")

    if thread.state in TERMINAL_STATES:
        raise IllegalTransition(
            f"Thread {thread_id!r} is in terminal state {thread.state!r}; "
            "no further transitions are permitted"
        )

    allowed = TRANSITIONS.get(thread.state, frozenset())
    if to_state != "abandoned" and to_state not in allowed:
        raise IllegalTransition(
            f"{thread.state!r} \u2192 {to_state!r} is not a valid transition. "
            f"Allowed from {thread.state!r}: {sorted(allowed | {'abandoned'})}"
        )

    from_state = thread.state
    thread.state = to_state
    thread.updated_at = datetime.datetime.now(datetime.timezone.utc)

    session.add(
        ThreadEvent(
            id=str(ULID()),
            thread_id=thread_id,
            source="internal",
            type="state.transition",
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            payload={"from_state": from_state, "to_state": to_state},
        )
    )

    return thread
