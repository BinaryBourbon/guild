# Roadmap

The captain-picard orchestrator reads this every cycle and writes the conversation id of each dispatched slice into "Now." Keep this file under one screen — if it grows, kill or defer something.

## Now

- **wedge-2-plan** — general-purpose-engineer (branch: wedge-2-plan, see PR #2)

## Next

_(empty — wedge-2-plan in flight; G1 gates all further dispatch)_

## Gated

- **G0** ✓ — Wedge 2 (Thread-First) selected. See `decisions/0002-wedge-2-thread-first.md`.
- **G1** — Wedge plan + ADRs approved by pr-reviewer. Plan must cover: thread schema, state machine, action primitive runtime, decision layer contract, context assembly, polling→webhook migration path.
- **G2** — First worker shippable end-to-end in a sandbox against a seeded issue. Human gates on whether this is real enough to point at this repo.
- **G3** — Self-hosting cutover: point the worker at live issues in this repo. Human gives go/no-go.
