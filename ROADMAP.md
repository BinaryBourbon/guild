# Roadmap

The captain-picard orchestrator reads this every cycle and writes the conversation id of each dispatched slice into "Now." Keep this file under one screen — if it grows, kill or defer something.

## Now

- **phase-0-framing** — customer-researcher (branch: phase-0-framing, see PR)

## Next

_(empty — phase-0-framing dispatched; G0 picks the wedge before anything else moves here)_

## Gated

- **G0** — Pick the first wedge from the framing PR.
- **G1** — Wedge plan + ADRs locked (event ingestion path, thread linkage, state persistence, action primitive runtime, worker decision contract).
- **G2** — First worker shippable end-to-end in a sandbox against a seeded issue.
- **G3** — Self-hosting cutover: point the worker at live issues in this repo.
