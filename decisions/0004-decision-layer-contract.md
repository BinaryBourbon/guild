# 0004 — Decision layer contract: tool_use for structured output, claude-sonnet-4-6 as default model

**Status:** Accepted — 2026-05-18

## Context

The decision layer (`docs/04`) must reliably produce structured output in the form `{ action, reasoning, params }`. Two sub-choices constrain every worker built on the platform: (1) how to elicit structured output from the LLM, and (2) which model to use as the default. Both are hard to change once workers are written against them.

## Decision

Use Anthropic's `tool_use` feature with `tool_choice: {"type": "tool", "name": "decide"}` to force structured JSON output. The `decide` tool's `input_schema` is the canonical contract — it is the source of truth for valid action types and param shapes. The model default is `claude-sonnet-4-6`.

Section 4 of every worker system prompt (Action vocabulary) is generated programmatically from the `DECIDE_TOOL` schema. It is never hand-written. This keeps the prompt and the action runner in sync: adding an action type requires updating the schema, the generated prompt section, and the action runner — in one PR.

## Consequences

- `tool_use` with `tool_choice: forced` guarantees the model returns a `tool_use` content block, not freeform text. Parsing is deterministic — no regex, no prompt sensitivity.
- The `reasoning` field is required and has a minimum length. A decision without reasoning is invalid and triggers `escalate`. This enforces `docs/04`'s requirement that reasoning is always written to the thread.
- `claude-sonnet-4-6` is the default across all workers. Individual workers may override in config, but must document the reason. Model upgrades propagate from the default config to all workers unless explicitly overridden.
- Every `decide()` call is logged before the action executes (append-only audit log). This enforces `docs/04`'s auditability requirement.

## Alternatives considered

- **JSON mode / response_format** — not available on the Claude API as of 2026-05-18. `tool_use` achieves the same result with explicit schema validation. Rejected in favor of `tool_use`.
- **Freeform text with regex or JSON extraction** — brittle; any rephrasing of the prompt risks breaking the parser. Rejected.
- **claude-opus-4-6 as default** — higher capability, but higher cost and latency. The decision layer runs on every event, including the frequent `ignore` case. Sonnet-4-6 is the right cost/quality tradeoff for bulk decisions; Opus is available as a per-worker override for workers that need it. Rejected as default.
- **Chain-of-thought + separate structured output call** — adds latency and cost per decision. The `reasoning` field in the single `tool_use` call achieves the same transparency goal. Rejected for phase 0; available as a per-worker option if needed.
