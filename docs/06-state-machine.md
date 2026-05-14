# 6. State Machine

## Purpose

The state machine tracks where Wade is with each piece of work. It gives Wade resilience — if processing is interrupted, or an event is delayed, Wade can reconstruct where it was and continue rather than starting over or duplicating work.

State lives on the [Thread Model](02-thread-model.md). Each thread has exactly one current state.

## States

```
                    ┌─────────────┐
                    │  unnoticed  │  Work exists but Wade hasn't seen it
                    └──────┬──────┘
                           │ relevant event received
                    ┌──────▼──────┐
                    │   noticed   │  Wade is aware, evaluating
                    └──────┬──────┘
                           │ Wade claims the work
                    ┌──────▼──────┐
                    │   claimed   │  Wade has self-assigned
                    └──────┬──────┘
                           │ implementation begins
                    ┌──────▼──────┐
             ┌──────│  executing  │──────┐
             │      └──────┬──────┘      │
             │             │ PR opened   │ blocked on question
             │      ┌──────▼──────┐      ▼
             │      │   pr_open   │  ┌─────────┐
             │      └──────┬──────┘  │ blocked │
             │             │         └────┬────┘
             │    ┌────────┴────────┐     │ human responds
             │    │                 │     └──► executing (resumes)
             │ approved        changes
             │    │            requested
             │    │                 │
             │    ▼                 └──► executing (loop)
             │  ┌──────┐
             │  │ done │
             │  └──────┘
             │
             ▼
         ┌───────────┐
         │ abandoned │  Wade gave up — reason logged
         └───────────┘
```

## State Descriptions

**`unnoticed`** — Default state. Work exists in the system but Wade has not acted on it.

**`noticed`** — A relevant event has arrived and Wade is evaluating whether to act. Typically a transient state — resolves quickly to `claimed` or back to `unnoticed`.

**`claimed`** — Wade has self-assigned the work and announced intent. The work is now Wade's responsibility.

**`executing`** — Active implementation is in progress. A CI/CD job is running or Wade is preparing one.

**`pr_open`** — Wade has opened a PR and is waiting for review. Wade is passive in this state unless @mentioned or a review event arrives.

**`blocked`** — Wade has asked a clarifying question or hit an obstacle it can't resolve alone. Waiting on human input. Wade should not take further action on this thread until unblocked.

**`done`** — Work is complete. PR merged, issue closed.

**`abandoned`** — Wade gave up. Reason logged to the thread. May happen due to repeated failures, unresponsive humans, or explicit instruction.

## Transitions

Transitions are triggered by:
- **Incoming events** — e.g., `pr.merged` → `done`, `pr.review_submitted (changes_requested)` → `executing`
- **Wade's own actions** — e.g., opening a PR → `pr_open`, posting a question → `blocked`

Illegal transitions are rejected. Wade cannot move directly from `unnoticed` to `executing` — it must claim work before beginning.

## Resilience

Because state is persisted on the thread, Wade can recover from failures:
- If an execution job crashes, the thread is still in `executing` — Wade can re-dispatch or check status on restart
- If a webhook is delayed, state prevents duplicate actions (don't claim work that's already claimed)
- If Wade restarts entirely, threads in non-terminal states are recovered and evaluated
