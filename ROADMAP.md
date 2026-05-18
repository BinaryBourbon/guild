# Roadmap

The captain-picard orchestrator reads this every cycle and writes the conversation id of each dispatched slice into "Now." Keep this file under one screen — if it grows, kill or defer something.

## Now

- **g2-slice-1-foundation** — general-purpose-engineer (branch: g2-slice-1-foundation, see PR #3)

## Next

- **g2-slice-2-state-machine** — SQLAlchemy models + state machine enforcement + thread/event/artifact/note CRUD
- **g2-slice-3-action-primitives** — GitHubClient with auth seam (item #7) + action primitives + run_primitive retry fix (item #1)
- **g2-slice-4-decision** — context assembly (assemble_context) + decision layer (decide() via tool_use)
- **g2-slice-5-e2e** — PollingEventSource + claiming loop + asyncio entry point (items #4, #5, #8) + process model docs + 12-factor wiring (item #9)

## Gated

- **G0** ✓ — Wedge 2 (Thread-First) selected. See `decisions/0002-wedge-2-thread-first.md`.
- **G1** ✓ — Engineering plan + ADRs approved. See `decisions/0003`, `0004`, `0005` and `plan/wedge-2-plan/`.
- **G2** — First worker shippable end-to-end in a sandbox. Stops when a worker can be dispatched against a seeded issue. Human decides if real enough to point at this repo.
- **G3** — Self-hosting cutover: point the worker at live issues in this repo. Human gives go/no-go.
