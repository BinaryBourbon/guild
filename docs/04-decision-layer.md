# 4. Decision Layer

## Purpose

Given a context packet, the decision layer answers: **should I act, and if so, what should I do?**

This is where the LLM lives. The decision layer is an LLM call with a structured prompt, a structured output schema, and enough surrounding logic to make it reliable and auditable.

## Input / Output

**Input**: the context packet from [Context Assembly](03-context-assembly.md)

**Output**:
```
{
  action:    "implement" | "ask_question" | "comment" | "claim" | "ignore" | "escalate",
  reasoning: string,   // Wade's explanation of why it chose this action
  params:    object    // action-specific parameters
}
```

The `reasoning` field is not just for debugging — it gets written as a context note on the thread, so future decisions have access to why prior choices were made.

## The Action Space

**`implement`** — begin or continue coding work. Triggers the execution pipeline with a specific task description.

**`ask_question`** — requirements are unclear or conflicting. Post a question (to GitHub issue, PR, or Slack thread) and wait for a response before proceeding. Moves thread state to `blocked`.

**`comment`** — acknowledge, update, or respond without taking substantive action. Used for status updates, confirmations, or light coordination.

**`claim`** — self-assign an unowned work item and announce intent to work on it.

**`ignore`** — this event doesn't warrant action. The most common output. Wade should be conservative — most events are noise relative to any given thread.

**`escalate`** — something is wrong that Wade can't resolve. Flag it to a human with a clear explanation.

## Conservatism

The `ignore` case is as important as the action cases. An agent that acts on everything becomes noise. Wade should have a high bar for taking action, especially for:

- Events on threads it doesn't own
- Ambiguous events where the right action isn't clear
- Events that arrive while the thread is in a waiting state

When in doubt, `ask_question` is preferable to guessing.

## Prompt Design

The system prompt for the decision layer encodes:
- Wade's role and behavioral guidelines
- How to interpret each event type
- When to ask vs. act
- How to write the `reasoning` field
- Wade's "voice" for any generated text (comments, questions)

Prompts are versioned. Changes to decision behavior are tracked as prompt changes, not code changes.

## Auditability

Every decision — including `ignore` decisions — is logged with the context packet and the full LLM response. This makes Wade's behavior inspectable and debuggable. When Wade does something unexpected, the audit log shows exactly what it saw and why it chose what it did.
