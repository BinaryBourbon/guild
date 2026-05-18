"""Decision layer: wraps Anthropic tool_use to produce structured actions.

Design (ADR 0004):
- Model: claude-sonnet-4-6 (configurable via GUILD_MODEL env var)
- tool_use with forced tool choice so the model always returns a
  structured action dict, never freeform text
- Mandatory `reasoning` field in every action so decisions are auditable
- Section 4 of the system prompt is auto-generated from DECIDE_TOOL schema
- Every decision is logged to thread_notes via log_decision() (audit trail)

The decide() function is pure from the caller's perspective:
- Input: thread context dict + Anthropic client + session
- Output: action name + params dict
- Side effect: writes a decision note (flushed, not committed)
"""
from __future__ import annotations

import os
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from guild.primitives.meta import log_decision

_DEFAULT_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Tool schema (Section 4 of system prompt is auto-generated from this)
# ---------------------------------------------------------------------------

DECIDE_TOOL: dict[str, Any] = {
    "name": "decide",
    "description": (
        "Select the next action to take on this thread. "
        "You MUST call this tool — do not respond with text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": (
                    "Explain why you chose this action given the thread state "
                    "and recent events. Required."
                ),
            },
            "action": {
                "type": "string",
                "enum": [
                    "claim_thread",
                    "create_branch",
                    "commit_and_push",
                    "open_pull_request",
                    "comment_on_issue",
                    "comment_on_pr",
                    "assign_to_self",
                    "add_label",
                    "update_thread_state",
                    "write_thread_note",
                    "wait",
                    "abandon",
                ],
                "description": "The action primitive to invoke.",
            },
            "params": {
                "type": "object",
                "description": "Parameters for the chosen action primitive.",
            },
        },
        "required": ["reasoning", "action", "params"],
    },
}

_SYSTEM_PROMPT = """\
You are Guild, an autonomous software development worker.
You operate by examining a thread — a structured record of a unit of work —
and deciding what action to take next.

Section 1: Your capabilities
You can read GitHub issues, create branches, commit code, open pull requests,
post comments, assign work to yourself, and manage thread state.

Section 2: Decision principles
- Prefer the smallest action that moves the thread forward
- Always explain your reasoning before acting
- If blocked with no clear path forward, mark the thread blocked and add a note
- Never abandon a thread without explaining why in the reasoning field

Section 3: Thread states
unnoticed → noticed → claimed → executing → pr_open → done
                                        → blocked
                                        → planned → done
Abandoned is reachable from any non-terminal state.

Section 4: Available actions (decide tool)
Call the `decide` tool with one of the following actions:
"""

# Append action list from DECIDE_TOOL schema to keep prompt + schema in sync
_ACTIONS = DECIDE_TOOL["input_schema"]["properties"]["action"]["enum"]
_SYSTEM_PROMPT += "\n".join(f"- {a}" for a in _ACTIONS)


def decide(
    context: dict[str, Any],
    *,
    anthropic_client: anthropic.Anthropic,
    session: Session,
    thread_id: str,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Ask the model what to do next and return (action, params).

    Calls the Anthropic API with forced tool_use so the model always
    returns a structured decide() call.  Logs the decision to the DB.

    Args:
        context: Output of assemble_context() for this thread.
        anthropic_client: Injected Anthropic client (for testability).
        session: SQLAlchemy session (for audit logging).
        thread_id: Thread to log the decision against.
        model: Override model ID (default: claude-sonnet-4-6).

    Returns:
        (action, params) tuple ready to be passed to run_primitive().

    Raises:
        RuntimeError: If the model returns an unexpected response format.
    """
    effective_model = model or os.environ.get("GUILD_MODEL", _DEFAULT_MODEL)

    response = anthropic_client.messages.create(
        model=effective_model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        tools=[DECIDE_TOOL],
        tool_choice={"type": "tool", "name": "decide"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Current thread context:\n\n"
                    f"State: {context['thread']['state']}\n"
                    f"Title: {context['thread']['title']}\n"
                    f"Anchor: {context['thread']['anchor_type']} {context['thread']['anchor_id']}\n\n"
                    f"Recent events ({len(context['events'])}):\n"
                    + _format_events(context["events"])
                    + f"\n\nNotes ({len(context['notes'])}):\n"
                    + _format_notes(context["notes"])
                    + f"\n\nArtifacts ({len(context['artifacts'])}):\n"
                    + _format_artifacts(context["artifacts"])
                    + "\n\nWhat should I do next?"
                ),
            }
        ],
    )

    # Extract tool_use block (forced, so always present)
    tool_block = next(
        (b for b in response.content if b.type == "tool_use" and b.name == "decide"),
        None,
    )
    if tool_block is None:
        raise RuntimeError(
            f"Model returned no 'decide' tool_use block. "
            f"Stop reason: {response.stop_reason}. "
            f"Content: {response.content!r}"
        )

    action_input: dict[str, Any] = tool_block.input
    reasoning: str = action_input.get("reasoning", "")
    action: str = action_input["action"]
    params: dict[str, Any] = action_input.get("params", {})

    # Audit log: write decision note (flush only — caller commits)
    log_decision(session, thread_id, reasoning=reasoning, action=action, params=params)

    return action, params


def _format_events(events: list[dict[str, Any]]) -> str:
    if not events:
        return "  (none)"
    return "\n".join(
        f"  [{e['timestamp']}] {e['source']}/{e['type']}: {_truncate(str(e['payload']), 200)}"
        for e in events
    )


def _format_notes(notes: list[dict[str, Any]]) -> str:
    if not notes:
        return "  (none)"
    return "\n".join(
        f"  [{n['note_type']}] {_truncate(n['body'], 300)}"
        for n in notes
    )


def _format_artifacts(artifacts: list[dict[str, Any]]) -> str:
    if not artifacts:
        return "  (none)"
    return "\n".join(
        f"  {a['artifact_type']}: {a['url']}"
        for a in artifacts
    )


def _truncate(s: str, max_len: int) -> str:
    return s if len(s) <= max_len else s[:max_len] + "..."
