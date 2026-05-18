"""Initial schema: threads, thread_events, thread_artifacts, thread_notes

Revision ID: 0001
Revises:
Create Date: 2026-05-18

Covers decisions/0003 (thread schema).  Two pr-reviewer items addressed here:
  #2 — threads_parent index for planned->done parent lookups
  #3 — 'observation' added to note_type CHECK alongside decision/status/error
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # threads: one row per unit of work
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE threads (
            id               TEXT PRIMARY KEY,
            anchor_type      TEXT NOT NULL,
            anchor_id        TEXT NOT NULL,
            anchor_url       TEXT NOT NULL,
            anchor_title     TEXT NOT NULL,
            state            TEXT NOT NULL DEFAULT 'unnoticed'
                             CHECK (state IN (
                                 'unnoticed', 'noticed', 'claimed', 'executing',
                                 'pr_open', 'blocked', 'planned', 'done', 'abandoned'
                             )),
            owner_type       TEXT CHECK (owner_type IN ('worker', 'human')),
            owner_id         TEXT,
            parent_thread_id TEXT REFERENCES threads(id),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # One thread per work item
    op.execute(
        "CREATE UNIQUE INDEX threads_anchor ON threads(anchor_type, anchor_id)"
    )

    # pr-reviewer item #2: partial index for planned->done parent queries
    # ("find all children of thread X" = WHERE parent_thread_id = X)
    op.execute("""
        CREATE INDEX threads_parent ON threads(parent_thread_id)
        WHERE parent_thread_id IS NOT NULL
    """)

    # ------------------------------------------------------------------
    # thread_events: normalized, durable event log
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE thread_events (
            id         TEXT PRIMARY KEY,
            thread_id  TEXT NOT NULL REFERENCES threads(id),
            source     TEXT NOT NULL,
            type       TEXT NOT NULL,
            actor_id   TEXT,
            actor_name TEXT,
            timestamp  TIMESTAMPTZ NOT NULL,
            payload    JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # PRIMARY KEY on id enforces dedup (INSERT ... ON CONFLICT (id) DO NOTHING)
    op.execute(
        "CREATE INDEX thread_events_by_thread ON thread_events(thread_id, timestamp DESC)"
    )

    # ------------------------------------------------------------------
    # thread_artifacts: PRs, branches, commits, comments the worker creates
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE thread_artifacts (
            id          TEXT PRIMARY KEY,
            thread_id   TEXT NOT NULL REFERENCES threads(id),
            type        TEXT NOT NULL,
            external_id TEXT NOT NULL,
            url         TEXT,
            title       TEXT,
            state       TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX thread_artifacts_by_thread ON thread_artifacts(thread_id, type)"
    )

    # ------------------------------------------------------------------
    # thread_notes: structured worker-authored context summaries
    # pr-reviewer item #3: 'observation' added alongside decision/status/error
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE thread_notes (
            id         TEXT PRIMARY KEY,
            thread_id  TEXT NOT NULL REFERENCES threads(id),
            author_id  TEXT NOT NULL,
            note_type  TEXT NOT NULL
                       CHECK (note_type IN ('decision', 'status', 'error', 'observation')),
            body       TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX thread_notes_by_thread ON thread_notes(thread_id, created_at DESC)"
    )


def downgrade() -> None:
    # Drop in reverse FK-dependency order
    op.execute("DROP TABLE IF EXISTS thread_notes")
    op.execute("DROP TABLE IF EXISTS thread_artifacts")
    op.execute("DROP TABLE IF EXISTS thread_events")
    op.execute("DROP TABLE IF EXISTS threads")
