## Context

Slices 1 and 2 merged green. Slice 3 was merged and immediately reverted: CI showed 10 failing tests (4 in `test_action_runner.py`, 6 in `test_meta_primitives.py`). Reference code for the reverted slice lives at commit `878db6b`. Branch from main at `6125be3`.

## Task

- Bring forward all slice-3 source files from `878db6b`: `src/guild/github_client.py`, `src/guild/primitives/__init__.py`, `src/guild/primitives/code.py`, `src/guild/primitives/communication.py`, `src/guild/primitives/meta.py`, `src/guild/primitives/work.py`
- Bring forward all slice-3 test files from `878db6b`: `tests/test_action_runner.py`, `tests/test_primitives.py`, `tests/test_meta_primitives.py`
- Run `pytest -v` locally and record the exact failure output
- Fix all failures before opening a PR. Two known bugs to start with:
  - **`test_meta_primitives.py`**: `_make_thread()` passes `title="test thread"` but `Thread` has no `title` field — use `anchor_title` and add the required `anchor_url`
  - **`meta.py::write_thread_note`**: calls `crud.write_note(session, thread_id=..., ...)` — `session` ends up as the `thread_id` positional arg and `author_id` is missing entirely; fix the call to match the actual signature `write_note(thread_id, author_id, note_type, body, session)`
  - **`test_action_runner.py`**: 4 of 5 tests fail — run pytest to get the exact assertions and fix
- Do NOT open a PR until `pytest -v` exits 0

## Acceptance

- `pytest -v` exits 0 locally (real Postgres, `DATABASE_URL` set) — all pre-existing tests still pass plus all 3 new test files green
- PR description names each test that was failing, its root cause, and the fix applied
- `gh pr checks <num>` shows every required check passing before requesting merge

## Out of scope

- Decision layer, context assembly (slice 4)
- Claiming loop, asyncio entry point, planned→done trigger (slice 5)
- Any changes to tests or source files from slices 1 and 2
- ROADMAP or ADR changes
