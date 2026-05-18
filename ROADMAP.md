# Roadmap

The captain-picard orchestrator reads this every cycle and writes the conversation id of each dispatched slice into "Now." Keep this file under one screen — if it grows, kill or defer something.

## Now

- **g2-slice-2-state-machine** — general-purpose-engineer (branch: g2-slice-2-state-machine, see PR #4)

## Next

- **g2-slice-3-action-primitives** — GitHubClient (auth seam, item #7) + action primitives + run_primitive retry fix (item #1)
- **g2-slice-4-decision** — context assembly + decision layer (decide() via tool_use)
- **g2-slice-5-e2e** — PollingEventSource + claiming loop + asyncio entry point (items #4, #5, #8, #9)

## Gated

- **G0** ✓ — Wedge 2 (Thread-First) selected.
- **G1** ✓ — Engineering plan + ADRs approved.
- **G2** — First worker shippable end-to-end in a sandbox. Human decides.
- **G3** — Self-hosting cutover.
