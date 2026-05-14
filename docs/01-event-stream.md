# 1. Normalized Event Stream

## Purpose

Wade receives events from multiple external systems — GitHub, Linear, Slack, CI pipelines. Each has a different schema, delivery mechanism, and reliability guarantee. The event stream's job is to normalize all of this into a single, durable, queryable feed before any agent logic touches it.

## Event Envelope

Every event, regardless of source, gets normalized into a common envelope:

```
{
  id:         string          // globally unique event ID
  source:     "github" | "linear" | "slack" | "ci"
  type:       string          // e.g. "issue.labeled", "message.mentioned", "pr.opened"
  timestamp:  datetime
  actor:      { id, name, handle, source_id }
  subject:    { type, id, url, title }   // what the event is about
  thread_id:  string          // which unit of work this belongs to (see Thread Model)
  raw:        object          // original payload, unmodified
}
```

The `thread_id` field is the critical link to the [Thread Model](02-thread-model.md). It may be set at ingestion time (if the link is obvious) or assigned later by the thread resolution process.

## Sources

### GitHub
- Delivered via webhook to a receiving endpoint
- Events: `issues.*`, `pull_request.*`, `issue_comment.*`, `push`, `check_run.*`
- Webhook secret validation required on every request

### Linear
- Delivered via webhook
- Events: issue created/updated/assigned/closed, comment created
- Maps cleanly to the issue side of the thread model

### Slack
- Delivered via Slack Events API
- Events: `app_mention`, `message.channels` (in monitored channels), DMs
- @mention events are particularly important — they represent humans directing Wade mid-stream

### CI / Execution Callbacks
- Wade dispatches work to CI runners; runners call back with status
- Events: execution started, execution completed, execution failed
- These close the loop on the [State Machine](06-state-machine.md)

## Durability

Webhooks are fire-and-forget — they can be dropped, duplicated, or delivered out of order. The receiving endpoints must write events to a durable queue before acknowledging receipt. Processing happens from the queue, not inline.

A Postgres table with a worker polling it is a sufficient starting point. Deduplication by event `id` handles duplicate deliveries. Ordering within a thread is handled by timestamp.

## What the Stream Is Not

The event stream is not where decisions are made. It is plumbing — ingestion, normalization, durability. Everything downstream (context assembly, decision layer) reads from it but the stream itself has no awareness of what events mean.
