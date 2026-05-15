# Guild

Guild is a platform for building autonomous workers that participate in the software development lifecycle.

## The Premise

Most AI coding tools today are **trigger systems** — an event arrives, a job runs, it's done. The bot has no memory of yesterday, no awareness of the related PR that's failing, no way to respond when you ask it to hold off in Slack.

Guild is built around a different premise: software development as something that autonomous **workers** can genuinely participate in. Workers that have persistent awareness of what's happening, exercise judgment about when and how to act, and communicate through the same channels humans use — GitHub, Slack, PR comments.

Define your workers. Guild handles the rest.

## Workers

A worker is a user-defined autonomous agent that runs on the Guild platform. Teams typically run several workers with different roles — one that triages incoming issues, one that implements `bot-ready` tickets, one that responds to review feedback, one that watches CI failures. They share platform infrastructure but have independent identities, decision logic, and scopes.

Guild does not prescribe what a worker does or how it reasons. It provides the plumbing — events, memory, context, actions, state — and workers define their own behavior on top of it.

## Architecture

Guild is built on eight components:

| # | Component | What it does |
|---|---|---|
| 1 | [Normalized Event Stream](docs/01-event-stream.md) | Unified envelope for events from all sources |
| 2 | [Thread Model](docs/02-thread-model.md) | Connects related events into coherent units of work |
| 3 | [Context Assembly](docs/03-context-assembly.md) | Builds the full picture before any decision is made |
| 4 | [Decision Layer](docs/04-decision-layer.md) | Interface workers implement to receive context and return actions |
| 5 | [Action Primitives](docs/05-action-primitives.md) | The concrete things workers can do in the world |
| 6 | [State Machine](docs/06-state-machine.md) | Tracks where a worker is with each piece of work |
| 7 | [Social Presence](docs/07-social-presence.md) | Per-worker identity across GitHub and Slack |
| 8 | [Work Claiming](docs/08-work-claiming.md) | Proactive initiative — workers picking up work unprompted |

## What Makes This Different From a Trigger System

Three things separate autonomous workers from bots that fire and forget:

**Memory across events.** A PR opened, a review requested, a Slack message asking for an update, a merge — these are all the same thread of work. Guild connects them over time so every decision a worker makes is informed by what came before.

**Initiative, not just reaction.** Workers can browse available work, decide something is in scope, claim it, and start — without being explicitly triggered.

**Social presence.** Workers communicate through the same channels humans do. They announce what they're picking up, ask questions when requirements are unclear, and follow up. They feel like team members because they behave like them.
