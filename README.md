# Wade

Wade is an autonomous agent that participates in the software development lifecycle.

## The Premise

Most AI coding tools today are **trigger systems** — an event arrives, a job runs, it's done. The bot has no memory of yesterday, no awareness of the related PR that's failing, no way to respond when you ask it to hold off in Slack.

Wade is built around a different premise: an AI that is a **participant**. It has persistent awareness of what's happening across the engineering org, exercises judgment about when and how to act, and communicates through the same channels humans use — GitHub, Slack, PR comments.

The goal is not to automate individual tasks but to have something that can autonomously move work forward across its full lifecycle: picking up an issue, asking clarifying questions, writing code, opening a PR, responding to review, and shipping.

## Architecture

Wade is built on eight components:

| # | Component | What it does |
|---|---|---|
| 1 | [Normalized Event Stream](docs/01-event-stream.md) | Unified envelope for events from all sources |
| 2 | [Thread Model](docs/02-thread-model.md) | Connects related events into coherent units of work |
| 3 | [Context Assembly](docs/03-context-assembly.md) | Builds the full picture before any decision is made |
| 4 | [Decision Layer](docs/04-decision-layer.md) | LLM-powered reasoning over assembled context |
| 5 | [Action Primitives](docs/05-action-primitives.md) | The concrete things Wade can do in the world |
| 6 | [State Machine](docs/06-state-machine.md) | Tracks where Wade is with each piece of work |
| 7 | [Social Presence](docs/07-social-presence.md) | Wade's identity across GitHub and Slack |
| 8 | [Work Claiming](docs/08-work-claiming.md) | Proactive initiative — picking up work unprompted |

## What Makes This Different From a Trigger System

Three things separate an autonomous participant from a bot that fires and forgets:

**Memory across events.** A PR opened, a review requested, a Slack message asking for an update, a merge — these are all the same thread of work. Wade connects them over time so every decision is informed by what came before.

**Initiative, not just reaction.** Wade can browse available work, decide something is in scope, claim it, and start — without being explicitly triggered.

**Social presence.** Wade communicates through the same channels humans do. It announces what it's picking up, asks questions when requirements are unclear, and follows up. It feels like a team member because it behaves like one.
