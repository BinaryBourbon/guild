# 0006 — asyncio race condition between concurrent on_event dispatches

**Status:** Accepted — 2026-05-18

## Context

Both `PollingEventSource` and `ClaimingLoop` call the `on_event` handler
(which calls `run_event`) via `asyncio.to_thread`.  Because both sources
run inside the same asyncio event loop, two events for the same thread can
be dispatched concurrently.  The sequence looks like:

```
[Thread A] PollingEventSource fires on_event(thread_42, ev1)
[Thread B] ClaimingLoop fires on_event(thread_42, ev2)  ← overlaps with A

[A] assemble_context → decide → Anthropic API call (cost incurred)
[B] assemble_context → decide → Anthropic API call (cost incurred)
[A] transition(thread_42, 'claimed') + SELECT FOR UPDATE → succeeds, commits
[B] transition(thread_42, 'claimed') + SELECT FOR UPDATE → raises IllegalTransition
    (thread is already in 'claimed'; 'noticed'→'claimed' already done)
[B] except block: session.rollback()  ← B's work is undone, no corruption
```

This arises in G2 because:
- `asyncio.to_thread` creates a new OS thread per call with no per-thread
  serialisation.
- `run_event` takes a `SELECT FOR UPDATE` inside a transaction but the lock
  is only acquired at the `state_machine.transition` call, after the
  (expensive) Anthropic API call has already returned.
- There is no per-thread-id dispatch queue or coordinator to prevent two
  concurrent calls for the same thread ID.

## Decision

Accept the race for G2 (sandbox scope).  The existing `IllegalTransition`
exception handler in `run_event` already rolls back the losing transaction,
so the outcome is always consistent: at most one of the two concurrent
events wins and commits; the other is silently discarded.  No DB corruption
or state incoherence can result.  The cost is one wasted Anthropic API call
per race occurrence.

No code change is required now.  This ADR documents the known behaviour so
future engineers understand why an occasional `IllegalTransition` log line
is expected and not a bug.

## Consequences

- Occasional `IllegalTransition` log entries are normal during periods of
  overlapping polling and claiming cycles; they are not actionable in G2.
- Each race wastes one Anthropic API call.  At G2 sandbox volumes (< 50
  threads, 300 s claim interval, 120 s poll interval) this cost is
  negligible.
- The duplicate Anthropic call is the only observable side effect.  DB state
  remains correct because the row-level lock (`SELECT FOR UPDATE`) ensures
  only one transition commits.

## Alternatives considered

- **Per-thread dispatch queue** — each thread ID maps to an `asyncio.Queue`;
  `on_event` enqueues the event and a single consumer coroutine drains it
  sequentially.  Eliminates the race entirely.  Deferred to G3: adds
  non-trivial bookkeeping (queue lifecycle, memory management for idle
  threads) and the G2 volume does not justify it.
- **Global asyncio Lock / Semaphore per thread ID** — lighter than a queue;
  the second `on_event` for the same thread blocks until the first finishes.
  Still wasted latency; does not eliminate the extra Anthropic call because
  both callers have already decided to call `decide()` before blocking.  Not
  meaningfully better than the current approach for G2.
- **Coordinator actor** — a single coroutine owns all thread dispatch;
  `on_event` sends events to it and it serialises per thread.  Clean
  architecture, fits well with an actor model.  Deferred to G3 alongside
  the webhook migration (ADR 0005), where a coordinator can absorb both
  concerns at once.
