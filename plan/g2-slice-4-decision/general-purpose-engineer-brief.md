## Context

Slices 1-3 merged green. Main is at `8fcc30d`. Slice 4 was previously merged and reverted (it built on broken slice 3 code). Reference code at commit `a816f9e`. Branch from main at `8fcc30d`.

## Task

- Bring forward from `a816f9e`: `src/guild/context.py`, `src/guild/decision.py`, `tests/test_context.py`, `tests/test_decision.py`
- Fix the following bugs before opening a PR (slice 3 fixes ripple through):

**`src/guild/context.py`:**
- `"title": thread.title` — `Thread` has no `title` attribute; use `thread.anchor_title`
- `"artifact_type": a.artifact_type` — `ThreadArtifact` has no `artifact_type` attribute; use `a.type`

**`tests/test_context.py`:**
- `from python_ulid import ULID` — repo uses `ulid` package; change to `from ulid import ULID`
- `_make_thread` passes `title="test"` — no such field; use `anchor_title="test"` + `anchor_url="https://github.com/repo/owner/issues/42"`
- `ThreadNote(...)` missing `author_id` (required non-null column); add `author_id="worker"`
- `ThreadArtifact(... artifact_type="pull_request", ...)` — field is `type`; change to `type="pull_request"`

**`tests/test_decision.py`:**
- `from python_ulid import ULID` — change to `from ulid import ULID`
- `_make_thread` passes `title="Fix the bug"` — use `anchor_title="Fix the bug"` + `anchor_url="https://github.com/owner/repo/issues/1"`

- Run `pytest -v` locally against real Postgres; confirm all tests pass (including all prior-slice tests)
- Do NOT open a PR until `pytest -v` exits 0

## Acceptance

- `pytest -v` exits 0 locally (real Postgres)
- PR description names each failing test, its root cause, and the fix applied
- `gh pr checks <num>` all passing before requesting merge

## Out of scope

- Claiming loop, asyncio entry point, planned→done trigger (slice 5)
- Any changes to slices 1-3 source or test files
- ROADMAP or ADR changes
