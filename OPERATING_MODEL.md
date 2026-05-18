# Operating Model

This is the bible the [`captain-picard`](https://github.com/jhgaylor/agent-specs/blob/main/agents/teams/captain-picard/captain-picard.yml) orchestrator reads at the start of every conversation. Keep it tight — anything here that drifts from reality will mislead every dispatch downstream.

---

## Product

**Name:** Guild

**Description:** Guild is a platform for building autonomous workers that participate in the software development lifecycle. Teams define workers — agents with persistent awareness, judgment, and presence across GitHub, Slack, and Discord — and Guild provides the plumbing: event ingestion, thread memory, context assembly, action primitives, and state. The architectural reference is the eight component docs under [`docs/`](docs/), starting at [`docs/01-event-stream.md`](docs/01-event-stream.md).

**Success metric:** Guild is used to build Guild. A Guild worker, running on the Guild platform, claims an issue in this repo, opens a PR that passes verification, and gets merged — with the thread model preserving context across the full claim → PR → review → merge cycle.

## Roles

The captain-picard fleet (from [`jhgaylor/agent-specs`](https://github.com/jhgaylor/agent-specs)) has eight specialists. This team uses the subset below; others are dropped until they earn their keep.

- `general-purpose-engineer` — for typical feature, bug, and refactor work on the platform components (event ingestion, thread model, state machine, action runners, worker runtime).
- `pr-reviewer` — for PRs that touch core invariants (thread linkage, state transitions, action primitive contracts, verification gate) where a second opinion is worth the latency.
- `reliability-engineer` — for the worker runtime itself: durability of the event queue, recovery from interrupted executions, observability across the loop.
- `customer-researcher` — when evaluating whether a planned platform capability matches what real worker authors need before building it. Until Guild has external worker authors, the "customer" is the team writing Guild's own first worker.
- `release-validator` — for gating platform deploys once Guild is running its own worker.

(Designer, growth-marketer, and product-analyst are dropped for now — no UI surface, nothing external to launch, no users to analyze.)

## Gates

The orchestrator stops at every gate listed below and waits for the human operator to make the call. Don't add gates the team won't actually defend — every extra gate is friction.

- **G0** — Pick the first wedge. What is the minimum implementation of Guild (which components, in what depth) that lets a Guild worker claim and ship a real issue in this repo? Stops after `phase-0-framing`.
- **G1** — Wedge plan and ADRs locked. Stops after the engineering plan covers the load-bearing pieces (event ingestion path, thread linkage, state persistence, action primitive runtime, worker decision contract) and ADRs exist for any choice that constrains future work.
- **G2** — First worker shippable. Stops when the wedge is implemented end-to-end and a worker can be dispatched against a seeded issue in a sandbox. Human gates on whether this is real enough to point at this repo.
- **G3** — Self-hosting cutover. Stops before pointing the worker at live issues in this repo. Human gives go/no-go on running Guild against Guild.

## Brief format

The orchestrator dispatches specialists with a written brief at `plan/<slice>/<role>-brief.md`. Keep briefs under 30 lines.

```
## Context
<2–4 lines — what slice, what's been decided, what specialist needs to know>

## Task
<bullets — concrete deliverables>

## Acceptance
<bullets — how the orchestrator will verify the PR is done>

## Out of scope
<bullets — things the specialist must NOT do in this PR>
```

## Working agreements

- **Every change to this repo lands as a PR.** No specialist pushes to `main`. The orchestrator dispatches the work and dispatches review; the **operator (human, or operator-side agent driving captain-picard) performs the actual merge**.
- **The orchestrator pushes after every state change.** Briefs, ROADMAP edits, and ADRs that aren't pushed are invisible to the next conversation. Orchestrator ops commits (briefs, ROADMAP, ADR stubs) may land directly on `main` — only the code-bearing PRs require the merge gate below.
- **Two slices in flight max.** If `ROADMAP.md`'s "Now" has two entries, finish one before dispatching another.
- **Decisions become ADRs.** When something gets contentious or needs to constrain future work, write `decisions/NNNN-<title>.md`. Use [`decisions/0001-template.md`](decisions/0001-template.md).
- **The platform docs are the architectural source of truth.** Changes to invariants in [`docs/01-event-stream.md`](docs/01-event-stream.md) through [`docs/08-work-claiming.md`](docs/08-work-claiming.md) require an ADR before the implementing PR. The docs and the code do not get to drift.
- **Verification is mandatory.** Every code change ships with automated verification per [`docs/05-action-primitives.md#verification-requirement`](docs/05-action-primitives.md#verification-requirement). The orchestrator must reject specialist PRs that lack it — even when Guild itself is the thing being built.
- **Merge protocol — operator-gated, both criteria.** The orchestrator dispatches the work, dispatches `pr-reviewer` on every PR (no skipping for redos or "same scope as before" — every commit chain gets a fresh review), and **signals** the operator when both criteria below hold on the PR's latest commit:
  1. `gh pr checks <num>` shows every required check passing — no `FAILURE`, no `PENDING`, no missing checks.
  2. `pr-reviewer` has posted an approval verdict (`APPROVE` or equivalent positive language) on the **latest** commit. Approvals on older commits do not transfer; fixups require re-review.

  The **operator** performs the merge after independently verifying both criteria. The orchestrator does not call merge primitives or use `gh pr merge`. This rule exists because earlier orchestrator instances merged on approval alone with red CI, and merged a draft PR against an explicit operator hold; pulling the merge gate back to the operator removes the failure mode entirely.
- **Specialists do not call `open_pull_request` on a red branch.** Per [`docs/05`](docs/05-action-primitives.md#verification-requirement), the verification gate is local to the specialist: tests pass before the PR is opened. The operator's merge gate above is the second line of defense, not the first.
- **Drafts are operator holds.** If the operator converts a PR to `draft`, the orchestrator must not convert it back to ready. A draft means "operator is gating this PR for a reason captured in a comment"; the orchestrator's job is to wait, not to override.
- **Eat the dogfood.** Where building Guild requires functionality Guild will eventually provide (a queue, an event normalizer, a state store), prefer the dumbest version that lets a Guild worker use it over an abstraction that doesn't. Self-hosting is the success metric; it is also the design constraint.
