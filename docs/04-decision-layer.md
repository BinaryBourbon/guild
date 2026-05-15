# 4. Decision Layer

## Purpose

The decision layer is the interface between Guild's platform infrastructure and a worker's logic. Guild assembles context and delivers it; the worker decides what to do with it.

Guild defines the contract — what comes in, what must come out. Workers implement the logic — what to reason about, how to reason, and why.

## The Contract

**Input**: a context packet from [Context Assembly](03-context-assembly.md), delivered to the worker on every relevant event.

**Output** (required from the worker):
```
{
  action:    string,   // one of the platform action types, or a worker-defined extension
  reasoning: string,   // explanation of the decision — written to the thread as a context note
  params:    object    // action-specific parameters
}
```

The `reasoning` field is not optional. It gets written as a context note on the thread so future decisions — by this worker or others — have access to why prior choices were made.

## Platform Action Types

Guild provides a standard action vocabulary that maps directly to [Action Primitives](05-action-primitives.md):

**`implement`** — begin or continue coding work. Triggers the execution pipeline with a task description.

**`ask_question`** — requirements are unclear or conflicting. Post a question (to GitHub issue, PR, or Slack thread) and wait for a response. Moves thread state to `blocked`.

**`comment`** — acknowledge, update, or respond without taking substantive action. Status updates, confirmations, light coordination.

**`claim`** — self-assign an unowned work item and announce intent.

**`ignore`** — this event doesn't warrant action. The most important action type. Workers should return this most of the time.

**`escalate`** — something is wrong that the worker can't resolve. Flag it to a human with a clear explanation.

Workers may define additional action types that map to custom behavior, as long as they ultimately resolve to one or more action primitives.

## Worker Implementation

How a worker implements the decision layer is up to the worker author. Common approaches:

- **LLM-based**: pass the context packet to a language model with a system prompt that encodes the worker's role, judgment criteria, and voice. The model returns a structured action.
- **Rule-based**: deterministic logic over the context packet for simple, well-defined workers.
- **Hybrid**: rules for common cases, LLM for ambiguous ones.

Guild does not require a specific AI model or prompt structure. Workers own their decision logic entirely.

## What Guild Handles

Regardless of how a worker implements its logic, Guild handles:

- Delivering the context packet
- Validating the action response shape
- Routing the action to the appropriate primitive
- Writing the `reasoning` as a thread context note
- Logging every decision (including `ignore`) with the full context snapshot for auditability

## Conservatism

`ignore` is the most common correct answer. Workers that act on everything become noise. Worker authors should design their decision logic with a high bar for action, especially for:

- Events on threads the worker doesn't own
- Ambiguous events where the right action isn't clear
- Events that arrive while the thread is in a waiting state

When in doubt, `ask_question` is preferable to guessing.

## Auditability

Every decision — including `ignore` — is logged with the context packet and the full worker response. This makes worker behavior inspectable and debuggable. When a worker does something unexpected, the audit log shows exactly what it saw and what it decided.
