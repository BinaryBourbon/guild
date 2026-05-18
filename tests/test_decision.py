"""Tests for the decision layer.

All tests use a mock Anthropic client so no real API calls are made.
The mock returns a pre-baked tool_use response.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from ulid import ULID
from sqlalchemy.orm import Session

from guild.decision import DECIDE_TOOL, _DEFAULT_MODEL, decide, validate_decision
from guild.models import Thread, ThreadNote


def _make_tool_use_response(action: str, params: dict, reasoning: str = "test reasoning that is long enough") -> MagicMock:
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
        anchor_url="https://github.com/owner/repo/issues/1",
        anchor_title="Fix the bug",
        state="noticed",
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
        reasoning="The issue needs acknowledgement so I will post a comment.",
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
        reasoning="PR is ready to open because all checks pass.",
    )

    decide(ctx, anthropic_client=mock_client, session=session, thread_id=thread.id)
    session.flush()

    notes = session.query(ThreadNote).filter_by(thread_id=thread.id, note_type="decision").all()
    assert len(notes) == 1
    data = json.loads(notes[0].body)
    assert data["action"] == "open_pull_request"
    assert data["reasoning"] == "PR is ready to open because all checks pass."
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
    """decide() escalates (not raises) if model returns no decide tool_use block."""
    thread = _make_thread(session)
    ctx = _make_context(thread.id)

    mock_client = MagicMock()
    bad_response = MagicMock()
    bad_response.content = []  # no tool_use blocks
    bad_response.stop_reason = "end_turn"
    mock_client.messages.create.return_value = bad_response

    # decide() must NOT raise — it returns escalate instead
    action, params = decide(ctx, anthropic_client=mock_client, session=session, thread_id=thread.id)
    assert action == "escalate"
    assert params == {}


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
        "update_thread_state", "write_thread_note", "wait", "abandon", "escalate",
    }
    assert set(actions) == expected


# ---------------------------------------------------------------------------
# New tests for fix items 13-15
# ---------------------------------------------------------------------------

def test_validate_decision_rejects_missing_action():
    """Fix #13a: validate_decision rejects input missing 'action'."""
    ok, reason = validate_decision({"reasoning": "some reasoning here", "params": {}})
    assert not ok
    assert "action" in reason


def test_validate_decision_rejects_empty_reasoning():
    """Fix #13b: validate_decision rejects empty reasoning."""
    ok, reason = validate_decision({"action": "wait", "reasoning": "   ", "params": {}})
    assert not ok
    assert "reasoning" in reason


def test_validate_decision_rejects_wrong_params_shape():
    """Fix #13c: validate_decision rejects params that don't match PARAMS_SCHEMAS."""
    # create_branch requires branch_name: str; supply a wrong type
    ok, reason = validate_decision({
        "action": "create_branch",
        "reasoning": "creating a branch for this work",
        "params": {"branch_name": 123},  # int instead of str
    })
    assert not ok
    assert "branch_name" in reason or "params" in reason


def test_validate_decision_rejects_params_not_dict():
    """validate_decision rejects when params is not a dict."""
    ok, reason = validate_decision({
        "action": "wait",
        "reasoning": "no action needed here",
        "params": "not-a-dict",
    })
    assert not ok
    assert "params" in reason


def test_validate_decision_accepts_valid_input():
    """validate_decision returns (True, '') for valid input."""
    ok, reason = validate_decision({
        "action": "wait",
        "reasoning": "nothing to do right now",
        "params": {},
    })
    assert ok
    assert reason == ""


def test_decide_returns_escalate_on_validation_failure(session):
    """Fix #14: decide() returns ('escalate', {}) when validation fails; does not raise."""
    thread = _make_thread(session)
    ctx = _make_context(thread.id)

    mock_client = MagicMock()
    # Return a tool_use block with an invalid action
    bad_block = MagicMock()
    bad_block.type = "tool_use"
    bad_block.name = "decide"
    bad_block.input = {"action": "nonexistent_action", "reasoning": "whatever", "params": {}}
    bad_response = MagicMock()
    bad_response.content = [bad_block]
    bad_response.stop_reason = "tool_use"
    mock_client.messages.create.return_value = bad_response

    # Must not raise
    action, params = decide(ctx, anthropic_client=mock_client, session=session, thread_id=thread.id)
    assert action == "escalate"
    assert params == {}


def test_decide_escalate_writes_audit_note(session):
    """On validation failure, decide() still logs an escalate decision note."""
    thread = _make_thread(session)
    ctx = _make_context(thread.id)

    mock_client = MagicMock()
    bad_block = MagicMock()
    bad_block.type = "tool_use"
    bad_block.name = "decide"
    bad_block.input = {"action": "bad_action", "reasoning": "", "params": {}}
    bad_response = MagicMock()
    bad_response.content = [bad_block]
    bad_response.stop_reason = "tool_use"
    mock_client.messages.create.return_value = bad_response

    decide(ctx, anthropic_client=mock_client, session=session, thread_id=thread.id)
    session.flush()

    notes = session.query(ThreadNote).filter_by(thread_id=thread.id, note_type="decision").all()
    assert len(notes) == 1
    data = json.loads(notes[0].body)
    assert data["action"] == "escalate"
    assert "invalid model output" in data["reasoning"]


def test_system_prompt_contains_injection_guard():
    """Fix #15: system prompt contains prompt-injection guidance."""
    from guild.decision import _SYSTEM_PROMPT
    # Check for key phrases indicating the untrusted-data instruction
    assert "untrusted" in _SYSTEM_PROMPT.lower() or "UNTRUSTED" in _SYSTEM_PROMPT
    # Confirm it mentions event payloads as the source of untrusted data
    assert "payload" in _SYSTEM_PROMPT.lower() or "event" in _SYSTEM_PROMPT.lower()


def test_decide_tool_reasoning_has_min_length():
    """Fix #6: reasoning property must have minLength: 10."""
    reasoning_schema = DECIDE_TOOL["input_schema"]["properties"]["reasoning"]
    assert reasoning_schema.get("minLength") == 10


# ---------------------------------------------------------------------------
# Blocking fix 1: validate_decision enforces minLength: 10 on reasoning
# ---------------------------------------------------------------------------

def test_validate_decision_rejects_short_reasoning():
    """reasoning < 10 chars must be rejected even if non-empty."""
    ok, reason = validate_decision({"action": "wait", "reasoning": "ok", "params": {}})
    assert not ok
    assert "reasoning" in reason


# ---------------------------------------------------------------------------
# Blocking fix 2: fallback log_decision in except block never propagates
# ---------------------------------------------------------------------------

def test_decide_never_raises_when_log_decision_raises(session):
    """If log_decision raises (e.g. DB down), decide() must still return ('escalate', {})."""
    thread = _make_thread(session)
    ctx = _make_context(thread.id)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("API down")

    with patch("guild.decision.log_decision", side_effect=Exception("DB down")):
        action, params = decide(
            ctx, anthropic_client=mock_client, session=session, thread_id=thread.id
        )

    assert action == "escalate"
    assert params == {}
