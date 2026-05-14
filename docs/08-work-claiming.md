# 8. Work Claiming

## Purpose

Work claiming is Wade's initiative mechanism — the behavior that makes it proactive rather than purely reactive. Instead of waiting for a specific trigger, Wade periodically surveys available work, evaluates what's in scope, and picks something up.

This is what makes the difference between "a bot that fires when triggered" and "a teammate who moves work forward."

## The Claiming Loop

On a schedule (or triggered by specific signals like standup time, end of sprint, or a human invitation), Wade runs:

1. **Survey** — query available work matching its criteria across connected systems (Linear backlog, GitHub issues, unassigned tickets)
2. **Evaluate** — for each candidate, assess: is this clearly in scope? Are requirements clear enough to act on? Is someone else already on it?
3. **Select** — choose at most one item per cycle (avoid overcommitting)
4. **Claim** — self-assign, announce in the relevant channel, move thread to `claimed`
5. **Begin** — initiate the execution loop

## Claiming Criteria

What Wade will pick up is defined by policy, not learned from inference. Starting configuration:

- **Labels**: only issues tagged with a designated label (e.g., `wade-ready`, `bot`)
- **Repos**: only repos Wade has been explicitly granted access to
- **Priority**: prefer highest-priority unlabeled/unassigned work
- **Clarity**: skip issues with missing acceptance criteria or unresolved questions — ask for clarification instead
- **Size**: prefer smaller, well-defined tasks over large ambiguous ones

Policy is configurable per organization.

## Conflict Avoidance

Wade should not claim work that:
- Is already assigned to a human
- Has recent activity suggesting a human is working on it
- Wade has previously attempted and abandoned (unless explicitly re-invited)

When in doubt, don't claim — post a comment asking if the work is available.

## Announcing Intent

When Wade claims work, it announces it in the place where humans are watching — the Linear issue, the GitHub issue, and/or the relevant Slack channel:

> "Taking this — will open a PR when ready."

This gives humans a chance to intervene ("actually hold on" → Wade stands down) and creates visibility into what Wade is working on at any given time.

## Standing Down

Wade should yield immediately when:
- A human explicitly asks it to stop
- A human self-assigns the same work
- The requirements change significantly mid-execution

Standing down is not failure — it's correct behavior. Wade logs the reason and moves the thread to `abandoned` with a note explaining what happened and where it left things.

## Pace and Limits

Wade should not be running full-throttle at all times. Sensible defaults:
- Claim at most one item per claiming cycle
- Don't start new work while existing work is in `executing` or `pr_open` state (one thing at a time, initially)
- Slow down claiming frequency if recent executions have had high failure rates

These limits exist to keep Wade's output quality high and prevent it from becoming a source of noise.
