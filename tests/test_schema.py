"""Smoke tests: verify the initial migration creates the expected schema."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def test_all_tables_exist(db):
    result = db.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name IN ('threads', 'thread_events', 'thread_artifacts', 'thread_notes')
        ORDER BY table_name
    """))
    found = {row[0] for row in result}
    assert found == {"thread_artifacts", "thread_events", "thread_notes", "threads"}


def test_threads_state_defaults_to_unnoticed(db):
    db.execute(text("""
        INSERT INTO threads(id, anchor_type, anchor_id, anchor_url, anchor_title)
        VALUES ('t1', 'github_issue', 'owner/repo#1',
                'https://github.com/owner/repo/issues/1', 'Fix the thing')
    """))
    row = db.execute(text("SELECT state FROM threads WHERE id = 't1'")).fetchone()
    assert row[0] == "unnoticed"


def test_threads_anchor_unique(db):
    """Two threads cannot share the same (anchor_type, anchor_id) pair."""
    db.execute(text("""
        INSERT INTO threads(id, anchor_type, anchor_id, anchor_url, anchor_title)
        VALUES ('t2', 'github_issue', 'owner/repo#2',
                'https://github.com/owner/repo/issues/2', 'First')
    """))
    with pytest.raises(IntegrityError):
        db.execute(text("""
            INSERT INTO threads(id, anchor_type, anchor_id, anchor_url, anchor_title)
            VALUES ('t2b', 'github_issue', 'owner/repo#2',
                    'https://github.com/owner/repo/issues/2', 'Duplicate anchor')
        """))


def test_threads_invalid_state_rejected(db_engine):
    """Use a fresh connection so a PG constraint error doesn't taint the shared fixture."""
    with db_engine.connect() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(text("""
                INSERT INTO threads(id, anchor_type, anchor_id, anchor_url, anchor_title, state)
                VALUES ('t-bad', 'github_issue', 'owner/repo#99',
                        'https://github.com/owner/repo/issues/99', 'Bad', 'invalid_state')
            """))


def test_thread_events_dedup(db):
    """ON CONFLICT (id) DO NOTHING silently discards duplicate events."""
    db.execute(text("""
        INSERT INTO threads(id, anchor_type, anchor_id, anchor_url, anchor_title)
        VALUES ('t3', 'github_issue', 'owner/repo#3', 'https://x', 'Test')
    """))
    db.execute(text("""
        INSERT INTO thread_events(id, thread_id, source, type, timestamp)
        VALUES ('evt-1', 't3', 'github', 'issue.created', now())
    """))
    db.execute(text("""
        INSERT INTO thread_events(id, thread_id, source, type, timestamp)
        VALUES ('evt-1', 't3', 'github', 'issue.created', now())
        ON CONFLICT (id) DO NOTHING
    """))
    count = db.execute(
        text("SELECT COUNT(*) FROM thread_events WHERE id = 'evt-1'")
    ).scalar()
    assert count == 1


def test_thread_notes_accepts_observation(db):
    """pr-reviewer item #3: 'observation' is a valid note_type."""
    db.execute(text("""
        INSERT INTO threads(id, anchor_type, anchor_id, anchor_url, anchor_title)
        VALUES ('t4', 'github_issue', 'owner/repo#4', 'https://x', 'Test')
    """))
    db.execute(text("""
        INSERT INTO thread_notes(id, thread_id, author_id, note_type, body)
        VALUES ('n1', 't4', 'worker-0', 'observation',
                'Waiting on @alice for design sign-off before proceeding')
    """))
    row = db.execute(
        text("SELECT note_type FROM thread_notes WHERE id = 'n1'")
    ).fetchone()
    assert row[0] == "observation"


def test_threads_parent_index_exists(db):
    """pr-reviewer item #2: threads_parent index exists for planned→done lookups."""
    result = db.execute(text("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'threads'
          AND schemaname = 'public'
          AND indexname = 'threads_parent'
    """))
    assert result.fetchone() is not None, "threads_parent index missing from migration"
