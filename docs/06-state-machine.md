# 6. State Machine

## Purpose

The state machine tracks where a worker is with each piece of work. It gives workers resilience — if processing is interrupted, or an event is delayed, a worker can reconstruct where it was and continue rather than starting over or duplicating work.

State lives on the [Thread Model](02-thread-model.md). Each thread has exactly one current state.

## States

```
                    ┌─────────────┐
                    │  unnoticed  │  Work exists but no worker has acted on it
                    └──────┬──────┘
                           │ relevant event received
                    ┌──────▼──────┐
                    │   noticed   │  A worker is aware, evaluating
                    └──────┬──────┘
                           │ worker claims the work
                    ┌──────▼──────┐
                    │   claimed   │  A worker has self-assigned
                    └──────┬──────┘
                           │ work begins
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
         │ abandoned │  Worker gave up — reason logged
         └───────────┘
```

## State Descriptions

**`unnoticed`** — Default state. Work exists in the system but no worker has acted on it.

**`noticed`** — A relevant event has arrived and a worker is evaluating whether to act. Typically a transient state — resolves quickly to `claimed` or back to `unnoticed`.

**`claimed`** — A worker has self-assigned the work and announced intent. The work is now that worker's responsibility.

**`executing`** — The worker is actively doing work. This covers any form of active output: running a CI/CD job, writing code, decomposing an epic into sub-issues, triaging a backlog, or drafting a plan. The nature of the work depends on the worker type.

**`pr_open`** — The worker has opened a PR and is waiting for review. The worker is passive in this state unless @mentioned or a review event arrives. Applies to implementation workers; PM and other worker types typically transition directly from `executing` to `done`.

**`blocked`** — The worker has asked a clarifying question or hit an obstacle it can't resolve alone. Waiting on human input. The worker should not take further action on this thread until unblocked.

**`done`** — The worker has completed its responsibility for this work. For an implementation worker this means a PR was merged. For a PM worker this means sub-issues were created and the work has been handed off. The underlying issue may still be open in the tracker.

**`abandoned`** — The worker gave up. Reason logged to the thread. May happen due to repeated failures, unresponsive humans, or explicit instruction.

## Transitions

Transitions are triggered by:
- **Incoming events** — e.g., `pr.merged` → `done`, `pr.review_submitted (changes_requested)` → `executing`
- **Worker actions** — e.g., opening a PR → `pr_open`, posting a question → `blocked`, completing a plan → `done`

Illegal transitions are rejected. A worker cannot move directly from `unnoticed` to `executing` — it must claim work before beginning.

## Resilience

Because state is persisted on the thread, workers can recover from failures:
- If an execution job crashes, the thread is still in `executing` — the worker can re-dispatch or check status on restart
- If a webhook is delayed, state prevents duplicate actions (don't claim work that's already claimed)
- If Guild restarts entirely, threads in non-terminal states are recovered and evaluated
