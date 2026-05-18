## Context

Slices 1–4 merged green. Main is at `5ca510b`. This is the final G2 slice: it wires up the event loop and produces a runnable worker. After this slice a Guild worker can be dispatched against a seeded issue in a sandbox (G2 gate). Branch from main at `5ca510b`.

## Task

- **`src/guild/event_source.py`** — `EventSource` ABC (`start`, `stop`, `on_event`); `PollingEventSource` polls GitHub for active threads every `GUILD_POLL_INTERVAL_SECONDS` (default 120), normalizes new events, deduplicates via `INSERT ... ON CONFLICT (id) DO NOTHING` in `write_event`, calls registered `on_event(thread_id, event)` handler; async-compatible (item #8)
- **`src/guild/claiming.py`** — `ClaimingLoop` runs every `GUILD_CLAIM_INTERVAL_SECONDS` (default 300); queries GitHub for open issues with label `guild-claim` in `GUILD_REPO`; **conflict avoidance filters** (required): skip if assigned to a human, skip if another worker claimed it, **skip if this worker previously abandoned it** (item #5 — query `thread_events` or `thread.state == 'abandoned'` for threads owned by this worker against the same anchor); upserts Thread, transitions `unnoticed→noticed`, calls `on_event` handler
- **`src/guild/triggers.py`** — `check_planned_done(session, thread_id)` — called after any child thread transitions to terminal; if parent thread is in `planned` state and ALL child threads are in `done` or `abandoned`, transition parent to `done` (item #4); write `state.transition` event; call `session.flush()`
- **`src/guild/worker.py`** — `run_event(session, thread_id, event, github_client, anthropic_client)` — the `on_event` handler body: calls `assemble_context` → `decide` → `run_primitive`; on `update_thread_state` action, also calls `check_planned_done` for the thread's parent (if any); wraps in a per-event transaction (commit on success, rollback on error, log and continue)
- **`src/guild/main.py`** — replace existing stub with `asyncio.run(main())` entry point; loads `Config`, creates `engine`/`session_factory`, constructs `GitHubClient(token_provider=lambda: config.github_token)` and `anthropic.Anthropic(api_key=config.anthropic_api_key)`, starts `PollingEventSource` + `ClaimingLoop`, registers `run_event` as the `on_event` handler (items #8, #9 partial)
- **`src/guild/config.py`** — extend `Config` with: `poll_interval: int` (default 120), `claim_interval: int` (default 300), `worker_id: str` (`GUILD_WORKER_ID` env var, required), `guild_repo: str` (`GUILD_REPO` env var, `owner/repo` format, required)
- **`render.yaml`** — Render web service: `type: web`, `runtime: python`, `startCommand: guild`, env var references for all required vars (item #9 Render deploy)
- **Tests** — `tests/test_event_source.py` (mock GitHub, verify dedup, verify `on_event` called for new events only), `tests/test_claiming.py` (verify each conflict-avoidance filter, verify `unnoticed→noticed` transition, verify abandoned-thread skip), `tests/test_triggers.py` (planned→done fires when all children terminal; does not fire if any child active; no-op if parent not planned)

## Acceptance

- `pytest -v` exits 0 locally (real Postgres) — all tests including prior slices
- `python -c "from guild.main import main"` imports without error
- `render.yaml` is present and valid YAML
- PR description names items #4, #5, #8, #9 and what was done for each
- `gh pr checks <num>` all passing before requesting merge

## Out of scope

- Webhook delivery (decisions/0005)
- Linear, Slack, Discord integrations
- Production monitoring, Render secrets management, custom worker claiming policies
- Any changes to slices 1–4 source or test files
