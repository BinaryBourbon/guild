# Phase 0 Wedge Framing

**Role:** customer-researcher  
**Customer:** the team writing Guild's own first worker  
**Constraint:** the success metric requires the thread model to preserve context across the full claim → PR → review → merge cycle — not just that a PR gets opened

---

## What every wedge must deliver

Regardless of which wedge is chosen, the following are non-negotiable by the time G2 is reached:

1. A worker **claims** a GitHub issue in this repo (self-assigns, announces intent)
2. A worker **implements** the issue and opens a PR that **passes automated verification**
3. The **thread model** holds context across the lifecycle — if the process restarts between claim and review, the worker knows what it already decided and why
4. A human can **merge** the PR

Wedges differ in which of these they prove first and what they defer.

---

## Wedge 1 — Stateless Sprint

> Prove the action contract works. Defer persistence entirely.

### Architectural bet
GitHub's own data (issue body, PR, comments, labels, CI status) is sufficient context for a worker to close a simple issue. A thread model can be added later without reworking the action primitives or decision layer.

### In scope
- **Decision layer**: LLM with structured `action / reasoning / params` output
- **Action primitives**: GitHub code actions (`create_branch`, `commit_and_push`, `open_pull_request`, `push_to_branch`, `comment_on_issue`, `comment_on_pr`), `assign_to_self`, `add_label`
- **Work claiming**: polling loop on GitHub issues filtered by label (`guild-claim`)
- **State tracking**: GitHub labels only — `guild:claimed`, `guild:pr-open`, `guild:done`
- **Verification**: CI must pass before PR opens (per `docs/05`)

### Stubbed
- **Thread model**: none — context reconstructed from GitHub API on every tick
- **Event stream**: REST polling every 2 min; no webhooks, no durable queue
- **Context assembly**: inline GitHub API calls, no persistence
- **State machine**: GitHub labels as a proxy; no formal machine, no Postgres
- **Social presence**: single GitHub App or PAT; no per-worker identity infrastructure

### First closeable issue
Label any issue in this repo `guild-claim` with clear acceptance criteria in the body. Worker polls → self-assigns + labels `guild:claimed` → implements with Claude SDK → CI runs → opens PR → polls PR for review → addresses review feedback → PR merged.

### What this proves
- Action primitives work end-to-end
- LLM decision layer produces valid structured output
- A Guild worker can actually close a real issue in this repo

### What this doesn't prove
- Context continuity: if the process restarts between claiming and review, the worker starts fresh — it may re-claim, duplicate work, or miss prior reasoning
- Thread model invariants: the success metric's continuity requirement is not met
- Event delivery reliability: polling is lossy under load

### Rework required before G3
High. The state-from-labels approach is a dead end. Thread model and event stream must be built from scratch before self-hosting is credible. Wedge 1 buys speed at the cost of rework.

---

## Wedge 2 — Thread-First

> Do persistence right before proving the full loop. Stub delivery.

### Architectural bet
The thread model is the load-bearing invariant in the success metric. Building it correctly now — before proving the full loop — means G1 ADRs have something real to constrain. Polling for event delivery is a scaffolding choice that can be replaced without touching the thread model.

### In scope
- **Thread model**: Postgres — threads, events, artifacts, state, context notes per `docs/02`
- **State machine**: all states per `docs/06` (`unnoticed → noticed → claimed → executing → pr_open → done / abandoned`); transitions enforced
- **Action primitives**: full code + communication set per `docs/05`
- **Context assembly**: query thread → assemble context packet per `docs/03`
- **Decision layer**: LLM with proper context packet; `reasoning` written as thread context note
- **Work claiming**: poll GitHub issues → write events to thread; proactive survey loop per `docs/08`
- **Verification**: CI must pass before PR opens

### Stubbed
- **Event stream**: GitHub REST polling only — no webhook endpoint, no normalization pipeline, no dedup queue; events written directly to thread on poll
- **Social presence**: single GitHub App; no per-worker identity infrastructure yet
- **Slack/Discord**: not in scope

### First closeable issue
Same observable outcome as Wedge 1: label `guild-claim` → worker polls → claims → implements → verifies → opens PR → addresses review → merged. But: context notes are stored on the thread in Postgres; if the process restarts mid-cycle, the worker reads prior decisions from the thread and continues rather than starting over. The success metric's continuity requirement is actually satisfied.

### What this proves
- Everything Wedge 1 proves
- Thread model design is validated against the real claim → PR → review → merge lifecycle
- Context continuity on restart works
- State machine transitions match the real GitHub event sequence

### What this doesn't prove
- Event delivery under failure: what happens when a webhook is dropped or delivered twice
- Per-worker social identity
- Context assembly at scale (long-running threads with many events)

### Rework required before G3
Medium. Event delivery (polling → webhooks + queue) and social presence are the main gaps. Neither requires touching the thread model or state machine. The thread model ADR decisions will constrain the event stream design, not the other way around.

---

## Wedge 3 — Event-Pipeline-First

> Nail the plumbing. Hardcode the logic.

### Architectural bet
Event delivery is the hardest component to get right and the one most likely to cause failures in production. Building the webhook endpoint, durable queue, and normalization first means everything downstream is built on a solid foundation. The decision layer can stay rule-based until the pipeline is proven.

### In scope
- **Event stream**: GitHub webhook endpoint + Postgres event queue + dedup by event ID + normalization into common envelope per `docs/01`
- **Thread model**: minimal — anchor + events + state (enough to track claimed/pr_open/done and avoid duplicate claiming)
- **State machine**: `unnoticed → noticed → claimed → pr_open → done`
- **Work claiming**: event-triggered (`issues.labeled` with `guild-claim`) — not proactive survey
- **Action primitives**: GitHub code + communication actions
- **Verification**: CI must pass before PR opens

### Stubbed
- **Decision layer**: rule-based only — `issue.labeled=guild-claim` → claim + implement; `pull_request.review_submitted=changes_requested` → implement; `pull_request.merged` → done
- **Context assembly**: last N events from thread; no summarization, no context packet structure
- **Thread model**: no context notes, no artifact graph; state + events only
- **Social presence**: single GitHub App
- **Slack**: not in scope

### First closeable issue
Apply label `guild-claim` to an issue → webhook fires → event normalized and queued → worker rule triggers → self-assigns → implements → CI runs → opens PR → `review_submitted` event arrives → rule triggers re-implement → PR approved → `pr.merged` event → thread state set to `done`.

### What this proves
- Webhook endpoint is reliable and handles duplicates correctly
- Event queue processes events in order within a thread
- The full event → queue → worker pipeline works end-to-end
- Thread creation and state tracking on inbound events is correct

### What this doesn't prove
- LLM decision layer (hardcoded rules are not what Guild ultimately runs)
- Context assembly (the decision layer has almost no context)
- Context continuity (no context notes; worker can't explain its prior reasoning)
- Proactive work claiming (reactive only)

### Rework required before G3
High on the logic side. Rule-based decision layer must be replaced with the LLM contract. Context assembly must be built. Thread model must be extended with notes and artifact graph. Event pipeline itself survives to production — but it's a smaller fraction of the total system than it first appears.

---

## Comparison

| | Wedge 1: Stateless | Wedge 2: Thread-First | Wedge 3: Event-First |
|---|---|---|---|
| **Time to first closeable issue** | Shortest | Medium | Medium |
| **Thread model per spec** | No — rework required | Yes | Partial — extend later |
| **Context continuity on restart** | No | Yes | No |
| **Success metric fully satisfied** | No (continuity gap) | Yes | No (logic gap) |
| **LLM decision layer** | Yes | Yes | No |
| **Event delivery durability** | No | No | Yes |
| **Rework before G3** | High (persistence) | Medium (delivery) | High (decision layer) |
| **G1 ADR surface** | Large (everything) | Medium (delivery design) | Large (logic design) |

---

## The question for G0

All three wedges eventually need everything. The wedge choice is a sequencing bet:

- **Wedge 1** bets that proving the action contract quickly is worth reworking persistence later. Pick this if you need to demonstrate the loop closes as fast as possible and accept that G1 will be heavy.
- **Wedge 2** bets that getting thread model invariants right before proving the loop is worth an extra sprint. Pick this if context continuity is core to what you're trying to demonstrate and you want G1 ADRs to have a real design to constrain.
- **Wedge 3** bets that the event pipeline is the hardest unsolved problem and should be proven first. Pick this if you expect event delivery to be the primary source of production failure and want it de-risked before building logic on top.
