## Context

Phase 0. Repo just bootstrapped; eight component docs (`docs/01` through `docs/08`) define the full platform architecture. Success metric: a Guild worker running on the Guild platform claims an issue in this repo, opens a verified PR, and gets merged — with the thread model preserving context across the full claim → PR → review → merge cycle. The "customer" here is the team writing Guild's own first worker.

## Task

- Read all eight component docs as the authoritative description of each component
- Identify which components are load-bearing for the success metric vs. what can be stubbed or deferred
- Produce `plan/phase-0-framing/wedge-framing.md`: a side-by-side framing of 2–3 candidate wedges
- For each wedge: what's in scope, what gets stubbed, and what's the first issue a worker could actually close
- Surface the architectural bet each wedge is making and what it leaves unproven
- Do not recommend a wedge — present options clearly; the human picks at G0

## Acceptance

- `wedge-framing.md` exists with 2–3 meaningfully distinct wedges
- Each wedge answers all three questions: scope / stubs / first closeable issue
- Each wedge names its core architectural bet and what it doesn't prove
- A reader can make a go/no-go call on each wedge without asking follow-up questions
- Readable in one sitting (under two pages)

## Out of scope

- Writing code or implementation specs for any wedge
- ADRs (those come at G1, after the wedge is picked)
- Evaluating the Guild platform (guild.inevitable.fyi) infrastructure — assume it's available
- Slack/Discord social presence — GitHub-only is sufficient scope for phase 0
- Picking a winner — the framing presents options; the human decides
