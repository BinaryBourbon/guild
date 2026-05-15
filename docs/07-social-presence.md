# 7. Social Presence

## Purpose

Social presence is what makes a worker feel like a participant rather than a system. Guild provides the infrastructure for workers to have identities across GitHub and Slack — their own accounts, their own names, their own handles.

Each worker gets its own presence. A team running three workers might have `@implementer-bot`, `@reviewer-bot`, and `@triage-bot` as distinct identities in Slack and GitHub, each with a defined role that engineers understand.

This is not cosmetic. When a worker can be @mentioned, posts in the right threads, and communicates consistently, it becomes genuinely easier to work with. When it can't, it creates friction regardless of how good its output is.

## GitHub Identity (Per Worker)

Each worker is backed by a **GitHub App installation** with its own bot account. This means:
- Commits are authored by `[worker-name][bot]`
- PRs are opened under the worker's account
- Comments appear under the worker's account with the bot badge
- The worker can be @mentioned in issues and PRs
- Permissions are scoped to the repos the worker has been granted access to

Guild manages the GitHub App infrastructure. Worker authors configure the name, avatar, and repo scope.

## Slack Identity (Per Worker)

Each worker is backed by a **Slack App bot user**. This means:
- The worker can be @mentioned in any channel it's in
- The worker can post messages and reply in threads
- DMs to the worker are supported
- The worker appears in the member list like any other teammate

Workers should be added to the channels where the work they care about is discussed. A worker focused on implementation doesn't need to be in `#marketing`.

## Voice

Each worker author defines the communication style for their worker. Guild provides defaults and a set of conventions, but workers own their voice.

Conventions that apply to all workers:

**Be brief.** Workers are agents in someone's workflow, not chatbots. Messages should be concise.

**Be explicit about state.** When a worker picks up work, it says so. When it's blocked, it says why. When it finishes, it says what it did. Humans should never have to wonder what a worker is doing.

**Ask, don't guess.** Ambiguous requirements get a specific question, not an assumption. The question should be short and answerable.

**Surface decisions.** Non-obvious choices — a particular approach, a trade-off, a workaround — get a brief explanation in the PR or a comment.

## Communication Templates

Guild provides default templates for recurring communication patterns. Worker authors can override these:

- **Claiming work**: "Taking this — will open a PR when ready."
- **Asking a question**: "Before I start: [specific question]? Waiting on this before proceeding."
- **Shipping**: "PR open at [url]. [1-2 sentences on approach and anything notable]."
- **Blocked**: "Blocked on: [reason]. [What I need from you, specifically]."
- **Responding to review**: "Addressed [feedback summary] in [commit sha]. Let me know if you want it done differently."

## Handling @Mentions

@Mentions are a first-class event type. When a worker is @mentioned:
- The mention is ingested as an event into the [Event Stream](01-event-stream.md)
- It is linked to the relevant thread if one exists
- The [Decision Layer](04-decision-layer.md) treats it as high-priority — a human is directly addressing this worker
- The worker responds in the same thread, typically within seconds

Mentions can redirect a worker mid-stream: "hold off on this", "don't bother with tests for now", "do it differently." These update thread context and may change state.

@Mentions addressed to *a different worker* are routed to that worker, not the current one.
