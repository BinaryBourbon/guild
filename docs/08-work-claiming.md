# 8. Work Claiming

## Purpose

Work claiming is the initiative mechanism — the behavior that makes workers proactive rather than purely reactive. Instead of waiting for a trigger, a worker periodically surveys available work, evaluates what's in scope, and picks something up.

Guild provides the claiming loop. Workers define their own claiming policy.

## The Claiming Loop

Guild runs the following loop on behalf of each worker, on a configurable schedule:

1. **Survey** — query available work across the worker's connected systems (Linear backlog, GitHub issues, etc.)
2. **Evaluate** — for each candidate, the worker's policy determines: is this in scope? Are requirements clear enough? Is someone else on it?
3. **Select** — at most one item per cycle
4. **Claim** — self-assign, announce in the relevant channel, move thread to `claimed`
5. **Begin** — initiate the execution loop

Steps 1, 3, 4, and 5 are handled by the platform. Step 2 is implemented by the worker.

## Worker-Defined Claiming Policy

Workers define what they will and won't pick up. Policy is explicit configuration, not learned inference. A policy specifies:

- **Scope**: which repos, which issue trackers, which projects
- **Filters**: labels, assignee state, issue type, priority thresholds
- **Clarity requirement**: whether to skip issues that lack acceptance criteria
- **Size preference**: whether to prefer small well-defined tasks over large ambiguous ones

Workers may also implement a custom evaluation function — logic beyond simple filters — that receives a candidate work item and returns a yes/no with reasoning. This function runs inside the decision layer contract: context in, structured response out.

## Conflict Avoidance

Guild enforces these constraints regardless of worker policy:

- Don't claim work already assigned to a human
- Don't claim work another worker has already claimed
- Don't claim work this worker has previously abandoned (unless explicitly re-invited)

When a constraint is tripped, the candidate is skipped silently. If the worker wants to surface the conflict, it can do so via a `comment` action.

## Announcing Intent

When a worker claims work, it announces in the relevant thread:

> "Taking this — will open a PR when ready."

This gives humans a chance to intervene before work begins. If a human responds negatively within a short window, the worker stands down before executing.

## Standing Down

A worker yields immediately when:
- A human explicitly asks it to stop
- A human self-assigns the same work
- The requirements change significantly mid-execution

Standing down is correct behavior, not failure. The worker logs the reason, moves the thread to `abandoned`, and notes where it left things so a human or another worker can continue.

## Pace and Limits

Guild enforces sensible defaults that worker authors can adjust:

- Claim at most one item per cycle
- Don't start new work while existing work is in `executing` or `pr_open` state
- Back off claiming frequency if recent executions have a high failure rate

These defaults exist to keep output quality high and prevent any single worker from flooding a repo with activity.
