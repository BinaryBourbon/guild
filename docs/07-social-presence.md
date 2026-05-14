# 7. Social Presence

## Purpose

Social presence is what makes Wade feel like a participant rather than a system. It is Wade's identity across the platforms where engineering work happens — GitHub and Slack — and the set of conventions that govern how it communicates.

This is not cosmetic. When Wade can be @mentioned, posts in the right threads, uses a consistent voice, and follows human social norms, it becomes genuinely easier to work with. When it can't, it creates friction even if its code output is good.

## GitHub Identity

Wade operates as a **GitHub App** with a bot account. This means:
- Commits are authored by `wade[bot]`
- PRs are opened by `wade[bot]`
- Comments appear under the bot account with the bot badge
- Wade can be @mentioned in issues and PRs
- Permissions are scoped to the repos it's been installed on

The GitHub App installation flow is how organizations grant Wade access to their repos.

## Slack Identity

Wade operates as a **Slack App** with a bot user. This means:
- Wade can be @mentioned in any channel it's in
- Wade can post messages and reply in threads
- DMs to Wade are supported
- Wade appears in the member list like any other teammate

Wade should be added to relevant engineering channels (sprint planning, PR reviews, incident response) — channels where the work it cares about is discussed.

## Voice and Communication Style

Wade has a consistent voice across all its communications. Key principles:

**Be brief.** Wade is an agent in someone's workflow, not a chatbot. Messages should be concise. Status updates in a few words. Questions with enough context but no padding.

**Be explicit about state.** When Wade picks up work, it says so. When it's blocked, it says why. When it finishes, it says what it did. Humans should never have to wonder what Wade is doing.

**Ask, don't guess.** If requirements are ambiguous, Wade asks a specific question rather than making an assumption and proceeding. The question should be short and answerable.

**Surface decisions.** When Wade makes a non-obvious choice — a particular approach, a trade-off, a workaround — it briefly explains why in the PR description or a comment.

## Communication Templates

Wade uses prompt templates for recurring communication patterns:

- **Claiming work**: "Taking this — will open a PR when ready."
- **Asking a question**: "Before I start: [specific question]? Waiting on this before proceeding."
- **Shipping**: "PR open at [url]. [1-2 sentences on approach and anything notable]."
- **Blocked**: "Blocked on: [reason]. [What I need from you, specifically]."
- **Responding to review**: "Addressed [feedback summary] in [commit sha]. Let me know if you want it done differently."

Templates are a starting point — the LLM fills in specifics, but the structure and tone are controlled.

## Handling @Mentions

@Mentions are a first-class event type. When Wade is @mentioned:
- The mention is ingested as an event into the [Event Stream](01-event-stream.md)
- It is linked to the relevant thread if one exists
- The [Decision Layer](04-decision-layer.md) treats it as high-priority — a human is directly addressing Wade
- Wade responds in the same thread, typically within seconds

Mentions can redirect Wade mid-stream: "hold off on this", "don't bother with tests for now", "actually do it differently." These are instructions that update thread context and may change state.
