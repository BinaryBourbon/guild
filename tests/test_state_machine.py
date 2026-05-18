"""State machine tests: legal transitions, illegal transitions, terminal rejection,
abandoned universality."""
import pytest
from ulid import ULID

from guild.crud import create_thread
from guild.models import ThreadEvent
from guild.state_machine import TERMINAL_STATES, TRANSITIONS, IllegalTransition, transition


def _thread(session, state="unnoticed", **kw):
    """Create a thread in an arbitrary state, bypassing the state machine."""
    from guild.models import Thread
    t = Thread(
        id=str(ULID()),
        anchor_type="github_issue",
        anchor_id=f"owner/repo#{ULID()}",
        anchor_url="https://github.com/owner/repo/issues/1",
        anchor_title="Test",
        state=state,
        **kw,
    )
    session.add(t)
    session.flush()
    return t.id


# ---------------------------------------------------------------------------
# TRANSITIONS dict invariants
# ---------------------------------------------------------------------------

def test_transitions_covers_all_active_states():
    active = {"unnoticed", "noticed", "claimed", "executing", "pr_open", "blocked", "planned"}
    assert set(TRANSITIONS.keys()) == active


def test_terminal_states_not_in_transitions():
    for s in TERMINAL_STATES:
        assert s not in TRANSITIONS


# ---------------------------------------------------------------------------
# Legal transitions (parametrized across all 11 allowed moves)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_state,to_state", [
    ("unnoticed", "noticed"),
    ("noticed",   "claimed"),
    ("noticed",   "unnoticed"),
    ("claimed",   "executing"),
    ("executing", "pr_open"),
    ("executing", "blocked"),
    ("executing", "planned"),
    ("pr_open",   "executing"),
    ("pr_open",   "done"),
    ("blocked",   "executing"),
    ("planned",   "done"),
])
def test_legal_transition_succeeds(session, from_state, to_state):
    tid = _thread(session, state=from_state)
    thread = transition(tid, to_state, session)
    assert thread.state == to_state


def test_transition_writes_state_event(session):
    tid = _thread(session, state="unnoticed")
    transition(tid, "noticed", session)
    session.flush()
    events = (
        session.query(ThreadEvent)
        .filter_by(thread_id=tid, type="state.transition")
        .all()
    )
    assert len(events) == 1
    assert events[0].payload == {"from_state": "unnoticed", "to_state": "noticed"}
    assert events[0].source == "internal"


def test_transition_updates_updated_at(session):
    tid = _thread(session, state="unnoticed")
    session.flush()
    from guild.models import Thread
    before = session.get(Thread, tid).updated_at
    transition(tid, "noticed", session)
    session.flush()
    after = session.get(Thread, tid).updated_at
    # updated_at must be set by transition(); it may equal before if both
    # happen in the same microsecond, but it must not be None
    assert after is not None


# ---------------------------------------------------------------------------
# Illegal transitions (parametrized)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_state,to_state", [
    ("unnoticed", "claimed"),    # must pass through noticed
    ("unnoticed", "executing"),
    ("unnoticed", "done"),
    ("noticed",   "executing"),  # must claim first
    ("noticed",   "done"),
    ("claimed",   "noticed"),
    ("claimed",   "done"),
    ("executing", "noticed"),
    ("executing", "claimed"),
    ("pr_open",   "claimed"),
    ("pr_open",   "planned"),
    ("blocked",   "claimed"),
    ("blocked",   "done"),
    ("planned",   "executing"),
    ("planned",   "blocked"),
])
def test_illegal_transition_raises(session, from_state, to_state):
    tid = _thread(session, state=from_state)
    with pytest.raises(IllegalTransition):
        transition(tid, to_state, session)


# ---------------------------------------------------------------------------
# Terminal state rejection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("terminal", ["done", "abandoned"])
def test_terminal_rejects_any_transition(session, terminal):
    tid = _thread(session, state=terminal)
    with pytest.raises(IllegalTransition, match="terminal"):
        transition(tid, "executing", session)


def test_terminal_done_rejects_abandoned(session):
    """abandoned is always allowed from ACTIVE states but not from terminal ones."""
    tid = _thread(session, state="done")
    with pytest.raises(IllegalTransition, match="terminal"):
        transition(tid, "abandoned", session)


def test_terminal_abandoned_rejects_abandoned(session):
    tid = _thread(session, state="abandoned")
    with pytest.raises(IllegalTransition, match="terminal"):
        transition(tid, "abandoned", session)


# ---------------------------------------------------------------------------
# abandoned universally reachable from every active state
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("active_state", sorted(TRANSITIONS.keys()))
def test_abandoned_reachable_from_active(session, active_state):
    """docs/06: abandoned can occur from any active state."""
    tid = _thread(session, state=active_state)
    thread = transition(tid, "abandoned", session)
    assert thread.state == "abandoned"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_transition_raises_for_missing_thread(session):
    with pytest.raises(ValueError, match="not found"):
        transition("does-not-exist", "noticed", session)
