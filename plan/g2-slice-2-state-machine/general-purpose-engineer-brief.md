## Context

Slice 1 merged: project skeleton, CI, Alembic migrations, four tables. Slice 2 builds the ORM layer and state machine on top of that schema. No primitives, no event ingestion, no decision layer — those are Slices 3–5.

## Task

- `src/guild/models.py` — SQLAlchemy 2.0 ORM models for Thread, ThreadEvent, ThreadArtifact, ThreadNote; relationships (back_populates); CheckConstraints and UniqueConstraints mirroring the migration; `from __future__ import annotations` for forward refs
- `src/guild/db.py` — `make_engine(database_url)` and `make_session_factory(engine)` wrappers; no production config loading (entry point handles that in Slice 5)
- `src/guild/state_machine.py` — `TRANSITIONS: dict[str, frozenset[str]]` covering all active states; `TERMINAL_STATES`; `IllegalTransition(Exception)`; `transition(thread_id, to_state, session)` with `session.get(..., with_for_update=True)`, terminal check, TRANSITIONS validation, `abandoned` always allowed from active states, updates `thread.state` + `thread.updated_at`, writes `state.transition` event, returns thread; does NOT commit
- `src/guild/crud.py` — `create_thread`, `get_thread`, `write_event`, `write_note`, `write_artifact`; all take a Session, call session.flush(), do NOT commit; document that write_event does not deduplicate (that is the polling loop’s job, Slice 5)
- `tests/conftest.py` — add `session` fixture (per-test sessionmaker, always-rollback teardown; tests must use flush() not commit())
- `tests/test_models.py` — ORM round-trips for all four models; parent–child thread relationship; relationship attributes accessible
- `tests/test_state_machine.py` — all legal transitions (parametrized); all illegal transitions raise IllegalTransition (parametrized); terminal states reject all transitions including `abandoned`; `abandoned` reachable from every TRANSITIONS key (dynamic parametrize from TRANSITIONS.keys()); transition writes state.transition event with from_state/to_state payload; ValueError for missing thread
- `tests/test_crud.py` — round-trip for each CRUD function

## Acceptance

- CI green (real Postgres, no mocks)
- State machine tests cover all 11 legal transitions, all illegal transitions, terminal rejection, abandoned universality
- All tests use the session fixture; none call session.commit()

## Out of scope

- GitHub API / GitHubClient (Slice 3)
- run_primitive retry logic (Slice 3)
- Decision layer (Slice 4)
- Polling loop or claiming loop (Slice 5)
