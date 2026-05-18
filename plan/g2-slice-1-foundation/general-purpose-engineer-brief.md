## Context

G1 approved. Engineering plan + ADRs locked in `plan/wedge-2-plan/`. Nine operator + pr-reviewer items must each appear in the PR that introduces the relevant code. Items addressed in this slice: #2 (threads_parent index), #3 (observation in note_type), #6 (pytest + real Postgres CI), #9 partial (12-factor config reading). Remaining items ship in their owning slices:

- Item #1 (retry-loop bug fix) → Slice 3
- Item #4 (planned→done trigger mechanism) → Slice 5
- Item #5 (claiming loop abandoned-thread filter) → Slice 5
- Item #7 (GitHubClient auth seam) → Slice 3
- Item #8 (asyncio process model documentation) → Slice 5
- Item #9 remainder (entry point + Render target) → Slice 5

## Task

- `pyproject.toml` — Python 3.12, hatchling build; runtime: sqlalchemy>=2.0, alembic>=1.13, psycopg[binary]>=3.2, httpx>=0.27, anthropic>=0.34, python-ulid>=2.0; dev: pytest>=8.3, pytest-asyncio>=0.24; entry point `guild = "guild.main:main"` (stub, wired in Slice 5)
- `src/guild/__init__.py` — empty
- `src/guild/config.py` — `load_config()` reads DATABASE_URL, GUILD_WORKER_GITHUB_TOKEN, ANTHROPIC_API_KEY, PORT from env; raises RuntimeError naming ALL missing required vars at once; PORT defaults to 8000
- `.github/workflows/ci.yml` — push + PR trigger; Postgres 16 service; `pip install -e ".[dev]"`; `alembic upgrade head`; `pytest -v`; CI must be green before any PR can be merged
- `tests/__init__.py` — empty
- `tests/conftest.py` — `db_engine` fixture (session-scoped, runs alembic upgrade head); `db` fixture (per-test Connection with always-rollback teardown for isolation)
- `tests/test_schema.py` — all four tables exist; state CHECK rejects invalid values; threads_anchor UNIQUE enforced; ON CONFLICT DO NOTHING dedup works for thread_events; note_type accepts 'observation'; threads_parent index exists
- `tests/test_config.py` — raises on missing vars; error message names all missing vars; succeeds with all set; PORT defaults to 8000; PORT read from env
- `alembic.ini` — script_location = migrations; sqlalchemy.url left empty (overridden by env.py)
- `migrations/env.py` — reads DATABASE_URL from os.environ; supports offline and online mode
- `migrations/script.py.mako` — standard Alembic template
- `migrations/versions/0001_initial_schema.py` — four tables + all indexes per decisions/0003; threads_parent index (item #2); 'observation' in note_type CHECK (item #3); downgrade drops in reverse FK order

## Acceptance

- `pytest -v` passes with real Postgres (no DB mocks anywhere)
- `alembic upgrade head` then `alembic downgrade base` both succeed cleanly
- All four tables exist with correct CHECK constraints, UNIQUE indexes, FK relationships (verified by tests)
- `load_config()` raises on missing vars and names all of them (verified by tests)
- CI workflow runs on PR open; merge is blocked if CI is red
- No worker logic, GitHub API calls, or Anthropic API calls in this slice

## Out of scope

- SQLAlchemy ORM models (Slice 2)
- GitHub API / GitHubClient (Slice 3)
- Decision layer or Anthropic SDK usage (Slice 4)
- Polling loop, claiming loop, or asyncio entry point (Slice 5)
- Render deploy configuration (Slice 5)
