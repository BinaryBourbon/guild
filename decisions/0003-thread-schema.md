# 0003 — Thread model schema: normalized tables over document store

**Status:** Accepted — 2026-05-18

## Context

The thread model (`docs/02`) is Guild's primary persistence layer. The schema must support: (1) appending events and notes at high frequency, (2) querying "all events for thread X ordered by timestamp" efficiently, (3) deduplicating events by ID on ingest, and (4) evolving field shapes as the platform grows without full migrations.

This ADR records the choice between normalized relational tables vs. a document-per-thread approach (single JSONB column or a document store).

## Decision

Use normalized Postgres tables: `threads`, `thread_events`, `thread_artifacts`, `thread_notes`. Each table has a ULID primary key and a `thread_id` foreign key. Indexes on `(thread_id, timestamp DESC)` for event queries. UNIQUE on `thread_events.id` for database-enforced deduplication.

Event-type-specific fields that don't belong in normalized columns live in a `payload JSONB` column on `thread_events`. The envelope (id, source, type, actor, timestamp) is normalized; the contents are not. This gives schema stability without sacrificing flexibility for new event types.

## Consequences

- Event queries are indexed lookups — no JSON traversal for common paths.
- Deduplication is enforced by the database UNIQUE constraint. No application-level dedup code needed; INSERT ON CONFLICT DO NOTHING is the primitive.
- Adding new event types requires no schema change (`type` is TEXT; new types just appear).
- Adding new normalized fields (e.g., a `priority` column on `threads`) requires an Alembic migration. This is the cost of the normalized approach — acceptable given the benefit of reliable queries.
- Alembic manages all migrations. No schema change ships without a migration file.

## Alternatives considered

- **Single JSONB column per thread (one document per thread)** — simpler initial write path, but event-level queries require JSON traversal; atomic dedup on individual events is not possible; hard to index at event granularity. Rejected.
- **MongoDB or another document store** — more flexible for evolving event shapes, but adds an operational dependency (Postgres is already required). Rejected — Postgres JSONB gives sufficient schema flexibility without the additional service.
- **Pure event sourcing (append-only log, no `threads` table, state computed from events)** — architecturally clean, but current thread state (`state`, `owner_id`) is queried on every poll cycle. Materializing state in the `threads` row avoids recomputing from the full event log each time. Rejected for phase 0; can be revisited if event sourcing becomes needed for auditability at scale.
