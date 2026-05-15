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
      ┌─────────────│  executing  │──────┐
      │             └──────┬──────┘      │
      │ sub-issues  │ PR opened         │ blocked on question
      │ created     │                   ▼
      ▼      ┌──────▼──────┐      ┌─────────┐
 ┌─────────┐  │   pr_open   │      │ blocked │
 │ planned │  └──────┬──────┘      └────┬────┘
 └────┬───┘       │               │ human responds
        │    ┌────────┴────────┐   └──► executing (resumes)
        │    │                 │
 all children  │ approved   changes
  terminal     │              requested
        │    │                 │
        │    ▼                 └──► executing (loop)
        └─►┌──────┐
           │ done │
           └──────┘

         ┌───────────┐
         │ abandoned │  (from any state)
         └───────────┘
```

## State Descriptions

**`unnoticed`** — Default state. Work exists in the system but no worker has acted on it.

**`noticed`** — A relevant event has arrived and a worker is evaluating whether to act. Typically a transient state — resolves quickly to `claimed` or back to `unnoticed`.

**`claimed`** — A worker has self-assigned the work and announced intent. The work is now that worker's responsibility.

**`executing`** — The worker is actively doing work. This covers any form of active output: running a CI/CD job, writing code, decomposing an epic into sub-issues, triaging a backlog, or drafting a plan. The nature of the work depends on the worker type.

**`planned`** — The work has been decomposed into sub-issues, each of which is now its own thread. The parent thread is waiting for all child threads to reach a terminal state. The owning worker is passive in this state — Guild watches child threads and drives the transition automatically.

**`pr_open`** — The worker has opened a PR and is waiting for review. The worker is passive in this state unless @mentioned or a review event arrives. Applies to implementation workers; PM workers transition from `executing` to `planned` instead.

**`blocked`** — The worker has asked a clarifying question or hit an obstacle it can't resolve alone. Waiting on human input. The worker should not take further action on this thread until unblocked.

**`done`** — Work is complete. For implementation workers this means a PR was merged. For planned threads this means all child threads have reached terminal states.

**`abandoned`** — The worker gave up. Reason logged to the thread. May happen due to repeated failures, unresponsive humans, or explicit instruction. Can occur from any active state.

## Transitions

Transitions are triggered by:
- **Incoming events** — e.g., `pr.merged` → `done`, `pr.review_submitted (changes_requested)` → `executing`
- **Worker actions** — e.g., opening a PR → `pr_open`, posting a question → `blocked`, creating sub-issues → `planned`
- **Guild automation** — e.g., all child threads terminal → parent transitions from `planned` to `done`

Illegal transitions are rejected. A worker cannot move directly from `unnoticed` to `executing` — it must claim work before beginning.

## Resilience

Because state is persisted on the thread, workers can recover from failures:
- If an execution job crashes, the thread is still in `executing` — the worker can re-dispatch or check status on restart
- If a webhook is delayed, state prevents duplicate actions (don't claim work that's already claimed)
- If Guild restarts entirely, threads in non-terminal states are recovered and evaluated
- If a `planned` thread's child completion event is missed, Guild can recheck child states on recovery
