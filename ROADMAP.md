# Roadmap

The captain-picard orchestrator reads this every cycle and writes the conversation id of each dispatched slice into "Now." Keep this file under one screen — if it grows, kill or defer something.

## Now

*(waiting at G2 gate — operator go/no-go required)*

## Next

*(G3 planning will follow operator G2 decision)*

## Gated

- **G0** ✓ — Wedge 2 (Thread-First) selected.
- **G1** ✓ — Engineering plan + ADRs approved.
- **G2** — **READY FOR OPERATOR DECISION.** All five slices merged green (`5765ba1`). Worker is runnable: polling event loop, claiming loop, context assembly, decision layer, action primitives, asyncio entry point, Render deploy config. Operator decides whether to dispatch against a seeded sandbox issue.
- **G3** — Self-hosting cutover.
