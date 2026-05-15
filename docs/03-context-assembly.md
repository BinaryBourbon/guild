# 3. Context Assembly

## Purpose

Before a worker makes any decision, it needs the full picture. Context assembly is the process of querying the thread model and producing a **context packet** — a structured summary of everything relevant to the current event.

This is what gets passed to the [Decision Layer](04-decision-layer.md). The quality of decisions a worker makes is directly proportional to the quality of context assembly.

## What Goes Into a Context Packet

```
{
  work_item: {
    title, description, acceptance_criteria,
    labels, priority, reporter, assignee
  },
  history: [
    // ordered list of significant prior events on this thread
    // not every raw event — summarized and filtered for relevance
  ],
  artifacts: {
    open_prs: [...],
    recent_commits: [...],
    failing_checks: [...]
  },
  conversations: [
    // relevant Slack messages, issue comments, PR review comments
    // prioritizing recent and unresolved
  ],
  worker_notes: [
    // context notes this worker has written to the thread
  ],
  current_event: {
    // the normalized event that triggered this assembly
  }
}
```

## Assembly Strategy

Not everything in the thread should go into the context packet — context windows are finite and stuffing them with noise degrades decision quality.

Filtering heuristics:
- **Recency**: prefer recent events over old ones
- **Unresolved**: prioritize things that haven't been addressed (open review comments, unanswered questions)
- **Authored by this worker**: always include the worker's prior actions and notes on this thread
- **Human instructions**: always include explicit directions from humans, regardless of age

For long-running threads, a summarization step may be needed — compressing older history into a paragraph rather than listing every event.

## When Assembly Runs

Context assembly runs on every event that reaches the decision layer. It is not cached across events — state changes between events, so a fresh assembly ensures decisions are made on current information.

Assembly is the main cost center in Guild's processing loop. The query over the thread model should be optimized. Summaries of older history can be cached and updated incrementally rather than rebuilt from scratch each time.

## Failure Modes to Avoid

**Missing the thread.** If the event hasn't been linked to a thread yet, assembly must either resolve the link or explicitly signal that context is incomplete. Deciding without context is worse than not deciding.

**Stale context.** If external state has changed (a PR was merged, a Slack message was sent) and the event stream hasn't caught up, the worker may act on outdated information. Assembly should note the freshness of each piece of context.

**Over-inclusion.** Passing every event in the thread verbatim fills the context window with noise. Assembly is an editorial function — it should produce a crisp brief, not a raw dump.
