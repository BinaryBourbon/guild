# 0005 — Polling→webhook migration: EventSource interface isolates delivery from thread model

**Status:** Accepted — 2026-05-18

## Context

Phase 0 uses GitHub REST API polling for event delivery. Webhooks are the production target (real-time, durable, dedup-friendly via the UNIQUE constraint on `thread_events.id`). This ADR records how the polling stub is designed so replacing it with webhooks requires minimal rework and zero changes to the thread model or decision layer.

## Decision

Introduce an abstract `EventSource` interface. The polling loop (`PollingEventSource`) is one implementation. The future webhook handler (`WebhookEventSource`) will be another. The decision cycle registers a handler via `EventSource.on_event()` and never calls the polling loop directly. Swapping implementations is a config change.

Deduplication lives in the database (UNIQUE on `thread_events.id`), not in the event source. Both polling and webhook sources can be naive about duplicates — INSERT ON CONFLICT DO NOTHING handles it. This means running both sources simultaneously during migration is safe: redundant events are silently discarded.

Event normalization (GitHub payload → `NormalizedEvent`) is a pure function: `normalize_github_event(raw) -> NormalizedEvent`. Both sources call it. It is tested independently of the delivery mechanism.

## Consequences

- Adding webhook delivery requires: (1) implementing `WebhookEventSource` (endpoint validates GitHub webhook secret, calls `on_event` handler with normalized event), (2) updating config. No thread model, state machine, context assembly, or decision layer changes.
- The normalization function is the only place GitHub-specific payload schema appears. It must be kept current with GitHub's actual webhook payload shapes. Tests for it are required before G2 implementation begins.
- Phase 0 poll latency is up to 2 minutes (configurable). This is acceptable for proving the loop; webhook delivery removes this latency without requiring a re-architecture.
- The migration strategy is: enable `WebhookEventSource`, leave `PollingEventSource` running briefly, confirm events arrive via both, disable polling. The overlap is safe because dedup is database-side.

## Alternatives considered

- **Inline polling in the decision cycle (no EventSource abstraction)** — simpler initially, but any delivery change requires modifying the decision cycle. Rejected — the coupling cost is too high given that delivery replacement is a known future step.
- **Message queue (Redis Streams, SQS, etc.) between webhook and decision cycle** — proper decoupling, handles backpressure. Adds an operational dependency. Rejected for phase 0 — Postgres is already the operational dependency; don't add another. Revisit at G3 if throughput or reliability requires it.
- **Separate microservice for event delivery** — clean separation of concerns, independent scaling. Operational overhead is disproportionate to phase 0 scale. Rejected; revisit at G3 when scale is known.
