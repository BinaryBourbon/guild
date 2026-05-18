## Context

G0 resolved: Wedge 2 (Thread-First) selected (`decisions/0002-wedge-2-thread-first.md`). Phase 0 success metric: a Guild worker claims an issue in this repo, opens a verified PR, gets it merged — with the thread model preserving context across the full claim → PR → review → merge cycle. Event delivery is stubbed as GitHub REST polling; the engineering plan must document the migration path. ADRs are required for any choice that constrains future work.

## Task

Produce the following files. Each must be detailed enough for an implementation sprint to start without clarifying questions.

- `plan/wedge-2-plan/engineering-plan.md` — covers all six areas:
  1. Thread model schema (Postgres: threads, events, artifacts, context notes)
  2. State machine (states, transitions, enforcement) per `docs/06`
  3. Action primitive runtime with error handling per `docs/05`
  4. Worker decision contract (LLM invocation, prompt structure, structured output schema, validation)
  5. Context assembly (context packet structure, assembly query, filtering strategy) per `docs/03`
  6. Polling-based event delivery stub + migration path to webhooks

- `decisions/0003-thread-schema.md` — thread table shape (normalized vs. flat, indexing)
- `decisions/0004-decision-layer-contract.md` — LLM invocation contract (model, prompt structure, output format, validation)
- `decisions/0005-polling-to-webhook-migration.md` — how the polling stub is designed for clean replacement

## Acceptance

- Engineering plan covers all six areas with enough specificity to begin implementation
- Three ADRs exist in standard template format (`decisions/0001-template.md`)
- Each ADR names alternatives considered and why they were rejected
- pr-reviewer has reviewed and the plan PR is approved before G1 closes

## Out of scope

- Writing implementation code (this is a plan PR — no code)
- Slack/Discord integration (GitHub-only for phase 0)
- Per-worker social presence infrastructure (single GitHub App is sufficient for phase 0)
- Automated verification (required on every code PR at G2 — not applicable here)
- Designing the webhook endpoint itself (G2 implementation task, not a G1 plan task)
