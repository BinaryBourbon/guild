"""Tests for the decision layer.

All tests use a mock Anthropic client so no real API calls are made.
The mock returns a pre-baked tool_use response.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from python_ulid import ULID
from sqlalchemy.orm import Session

from guild.decision import DECIDE_TOOL, _DEFAULT_MODEL, decide
from guild.models import Thread, ThreadNote


def _make_tool_use_response(action: str, params: dict, reasoning: str = "test reasoning") -> MagicMock:
    """Build a mock Anthropic response with a decide tool_use block."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "decide"
    tool_block.input = {"reasoning": reasoning, "action": action, "params": params}

    response = MagicMock()
    response.content = [tool_block]
    response.stop_reason = "tool_use"
    return response


def _make_context(thread_id: str, state: str = "noticed") -> dict:
    return {
        "thread": {
            "id": thread_id,
            "state": state,
            "title": "Fix the bug",
            "anchor_type": "github_issue",
            "anchor_id": "owner/repo#1",
            "owner_id": None,
            "parent_thread_id": None,
            "created_at": "2024-01-01T12:00:00+00:00",
            "updated_at": "2024-01-01T12:00:00+00:00",
        },
        "events": [],
        "notes": [],
        "artifacts": [],
    }


def _make_thread(session: Session) -> Thread:
    thread = Thread(
        id=str(ULID()),
        anchor_type="github_issue",
        anchor_id="owner/repo#1",
        state="noticed",
        title="Fix the bug",
    )
    session.add(thread)
    session.flush()
    return thread


# ---------------------------------------------------------------------------
# decide() happy path
# ---------------------------------------------------------------------------

def test_decide_returns_action_and_params(session):
    thread = _make_thread(session)
    ctx = _make_context(thread.id)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_tool_use_response(
        "comment_on_issue",
        {"owner": "o", "repo": "r", "issue_number": 1, "body": "on it"},
        reasoning="The issue needs acknowledgement.",
    )

    action, params = decide(ctx, anthropic_client=mock_client, session=session, thread_id=thread.id)
    assert action == "comment_on_issue"
    assert params["body"] == "on it"


def test_decide_uses_default_model(session):
    thread = _make_thread(session)
    ctx = _make_context(thread.id)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_tool_use_response("wait", {})

    decide(ctx, anthropic_client=mock_client, session=session, thread_id=thread.id)
    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == _DEFAULT_MODEL


def test_decide_forced_tool_choice(session):
    """tool_choice must be forced to 'decide' so model always returns structured output."""
    thread = _make_thread(session)
    ctx = _make_context(thread.id)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_tool_use_response("wait", {})

    decide(ctx, anthropic_client=mock_client, session=session, thread_id=thread.id)
    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["tool_choice"] == {"type": "tool", "name": "decide"}


def test_decide_logs_decision_note(session):
    """Every decide() call must write an audit note to the DB."""
    thread = _make_thread(session)
    ctx = _make_context(thread.id)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_tool_use_response(
        "open_pull_request",
        {"head": "feat-branch"},
        reasoning="PR is ready to open.",
    )

    decide(ctx, anthropic_client=mock_client, session=session, thread_id=thread.id)
    session.flush()

    notes = session.query(ThreadNote).filter_by(thread_id=thread.id, note_type="decision").all()
    assert len(notes) == 1
    data = json.loads(notes[0].body)
    assert data["action"] == "open_pull_request"
    assert data["reasoning"] == "PR is ready to open."
    assert data["params"] == {"head": "feat-branch"}


def test_decide_model_override(session):
    thread = _make_thread(session)
    ctx = _make_context(thread.id)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_tool_use_response("wait", {})

    decide(ctx, anthropic_client=mock_client, session=session, thread_id=thread.id, model="claude-haiku-4-5-20251001")
    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == "claude-haiku-4-5-20251001"


def test_decide_raises_on_missing_tool_block(session):
    """RuntimeError if model returns no decide tool_use block."""
    thread = _make_thread(session)
    ctx = _make_context(thread.id)

    mock_client = MagicMock()
    bad_response = MagicMock()
    bad_response.content = []  # no tool_use blocks
    bad_response.stop_reason = "end_turn"
    mock_client.messages.create.return_value = bad_response

    with pytest.raises(RuntimeError, match="no 'decide' tool_use block"):
        decide(ctx, anthropic_client=mock_client, session=session, thread_id=thread.id)


# ---------------------------------------------------------------------------
# DECIDE_TOOL schema
# ---------------------------------------------------------------------------

def test_decide_tool_has_reasoning_field():
    """reasoning field is required (ADR 0004 mandatory)."""
    props = DECIDE_TOOL["input_schema"]["properties"]
    assert "reasoning" in props
    required = DECIDE_TOOL["input_schema"]["required"]
    assert "reasoning" in required


def test_decide_tool_action_enum_is_complete():
    """Action enum should include all expected primitives."""
    actions = DECIDE_TOOL["input_schema"]["properties"]["action"]["enum"]
    expected = {
        "claim_thread", "create_branch", "commit_and_push", "open_pull_request",
        "comment_on_issue", "comment_on_pr", "assign_to_self", "add_label",
        "update_thread_state", "write_thread_note", "wait", "abandon",
    }
    assert set(actions) == expected
