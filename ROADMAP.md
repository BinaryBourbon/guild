# Roadmap

The captain-picard orchestrator reads this every cycle and writes the conversation id of each dispatched slice into "Now." Keep this file under one screen — if it grows, kill or defer something.

## Now

_(empty — orchestrator fills this on dispatch, with `<slice> — <role> (conv <id>)` per entry.)_

## Next

- **phase-0-framing** — pick the first wedge. The eight component docs under [`docs/`](docs/) describe the full platform; the wedge is the subset that lets a Guild worker claim and ship a real issue in this repo. Produce a side-by-side framing of 2–3 candidate wedges (e.g. "thinnest possible end-to-end" vs "thread model + state first, claiming later" vs "event ingestion + action runner only, hardcode the rest"), each with: what's in scope, what gets stubbed, what's the first issue a worker could actually close. Decide direction at G0. Dispatch as `customer-researcher` — the "customer" here is the team writing Guild's own first worker.

## Gated

- **G0** — Pick the first wedge from the framing PR.
- **G1** — Wedge plan + ADRs locked (event ingestion path, thread linkage, state persistence, action primitive runtime, worker decision contract).
- **G2** — First worker shippable end-to-end in a sandbox against a seeded issue.
- **G3** — Self-hosting cutover: point the worker at live issues in this repo.
