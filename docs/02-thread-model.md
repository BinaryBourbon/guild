# 2. Thread Model

## Purpose

The thread model is Wade's memory. It answers the question: "what is everything I know about this unit of work?"

Without it, every event is a fresh start. With it, Wade can reason across time — knowing that the issue it just got assigned has a related PR, that someone asked it a question in Slack three hours ago, and that it already attempted an implementation that was rejected in review.

## What a Thread Is

A **thread** represents a single unit of work across its full lifecycle. It has:

- **Anchor**: the canonical work item, typically a Linear issue or GitHub issue
- **Events**: all normalized events associated with this work, in order
- **Artifacts**: things created as part of the work (branches, PRs, commits, comments)
- **State**: current position in the [State Machine](06-state-machine.md)
- **Owner**: who/what currently holds this work (a human, Wade, or unassigned)
- **Context notes**: structured summaries Wade writes to itself as it works

## Linking Events to Threads

The hardest problem in the thread model is **linkage** — how does event X get assigned to thread Y?

Three mechanisms, in order of reliability:

### 1. Explicit References
Most reliable. A GitHub PR that mentions `Fixes #42` links itself to the issue #42 thread. A Slack message that includes a Linear URL links itself. These are parsed at ingestion time.

### 2. Agent-Maintained Links
When Wade takes an action — opens a branch, creates a PR, posts a Slack message — it records the link itself. "I opened PR #17 for issue #42." This is the primary mechanism for keeping artifacts connected to their thread.

### 3. Heuristics
Fallback only. Same repository, same label, same time window, same actor. Fragile and should not be relied on. Flag uncertain links for human confirmation rather than silently guessing.

## The Thread Graph

A thread is best modeled as a lightweight graph rather than a flat list:

```
Linear Issue #42 (anchor)
  ├── event: issue.created
  ├── event: issue.assigned → Wade
  ├── event: slack.mention ("can you take a look at this?")
  ├── artifact: branch "wade/issue-42-auth-fix"
  ├── artifact: PR #17
  │     ├── event: pr.opened
  │     ├── event: pr.review_requested
  │     ├── event: pr.review_submitted (changes requested)
  │     └── event: pr.review_submitted (approved)
  └── event: pr.merged
```

Entities (issues, PRs, users, repos) are nodes. Events and relationships are edges. Queries like "what review feedback has this work received?" or "has anyone commented in Slack since the last commit?" are graph traversals.

## Context Notes

Wade writes structured notes onto the thread as it works — not raw logs, but useful summaries:

- "Attempted approach: X. Reviewer said it was too complex. Trying Y instead."
- "Waiting on design confirmation from @alice before proceeding."
- "Tests are failing in CI because of a pre-existing flake, not my changes."

These notes are included in context assembly and prevent Wade from repeating mistakes or losing track of prior decisions.

## What the Thread Model Is Not

It is not a project management tool — it doesn't replace Linear or GitHub Issues. It is a read/write index that Wade uses to maintain coherent state across a fragmented landscape of external systems.
