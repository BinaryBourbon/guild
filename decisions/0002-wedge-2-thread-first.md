# 0002 — Wedge 2 (Thread-First) selected for Phase 0

**Status:** Accepted — G0 resolved 2026-05-18

## Context

Phase 0 framing (`plan/phase-0-framing/wedge-framing.md`) produced three candidate wedges. The deciding constraint was the success metric's continuity requirement: the thread model must preserve context across the full claim → PR → review → merge cycle. Wedge 2 is the only option that satisfies this on first close without rework.

## Decision

Proceed with Wedge 2: Thread-First. Build the Postgres thread model and state machine per `docs/02` and `docs/06` from the start. Use GitHub REST API polling for event delivery in phase 0 as explicit scaffolding — not an architectural commitment — with a documented migration path to webhooks (`decisions/0005-polling-to-webhook-migration.md`). Prove the full success metric end-to-end, including context continuity, before declaring G2 complete.

## Consequences

- Thread schema and state machine transition rules are load-bearing. ADRs are required before the first implementation PR (`decisions/0003-thread-schema.md`).
- Polling is explicitly temporary. The event delivery design must isolate the event source so polling can be replaced with webhooks without touching the thread model or decision layer (`decisions/0005`).
- The LLM decision layer contract (`decisions/0004-decision-layer-contract.md`) must be specified before implementation — prompt structure and structured output format are design constraints, not implementation details.
- First closeable issue arrives one sprint later than Wedge 1, but the full success metric is satisfied on first close.
- G1 delivers an engineering plan and three ADRs, reviewed by pr-reviewer before G1 closes.

## Alternatives considered

- **Wedge 1 (Stateless Sprint)** — Rejected. GitHub labels as state proxy and no persistent thread model mean context continuity is not satisfied. Success metric gap; high rework burden before self-hosting.
- **Wedge 3 (Event-Pipeline-First)** — Rejected. Rule-based decision layer defers the LLM contract that Guild is built around. Event delivery is well-understood; the decision layer is the novel piece. Proving the pipeline first inverts the risk order.
