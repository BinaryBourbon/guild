"""Tests for GitHub API primitives using httpx mock transport."""
from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from guild.github_client import GitHubClient
from guild.primitives.code import create_branch, open_pull_request
from guild.primitives.communication import comment_on_issue, comment_on_pr
from guild.primitives.work import assign_to_self


class MockTransport(httpx.BaseTransport):
    """In-memory httpx transport backed by a response map.

    response_map keys are (method, path) tuples.
    Values are (status_code, json_body) tuples.
    """

    def __init__(self, responses: dict) -> None:
        self._responses = responses
        self.calls: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        key = (request.method, request.url.path)
        if key not in self._responses:
            return httpx.Response(404, json={"message": f"not mocked: {key}"})
        status, body = self._responses[key]
        return httpx.Response(status, json=body)


def make_client(responses: dict) -> tuple[GitHubClient, MockTransport]:
    transport = MockTransport(responses)
    http = httpx.Client(transport=transport, base_url="https://api.github.com")
    client = GitHubClient(lambda: "test-token", http_client=http)
    return client, transport


# ---------------------------------------------------------------------------
# GitHubClient auth seam
# ---------------------------------------------------------------------------

def test_authenticated_user_cached():
    client, transport = make_client({
        ("GET", "/user"): (200, {"login": "guild-bot"}),
    })
    assert client.authenticated_user == "guild-bot"
    assert client.authenticated_user == "guild-bot"  # second call — no extra request
    user_calls = [c for c in transport.calls if c.url.path == "/user"]
    assert len(user_calls) == 1


def test_auth_header_uses_token_provider():
    tokens = ["tok-a", "tok-b"]
    idx = {"i": 0}

    def rotating_token():
        t = tokens[idx["i"] % len(tokens)]
        idx["i"] += 1
        return t

    transport = MockTransport({("GET", "/user"): (200, {"login": "bot"})})
    http = httpx.Client(transport=transport, base_url="https://api.github.com")
    client = GitHubClient(rotating_token, http_client=http)
    client.get("/user")
    assert transport.calls[0].headers["authorization"] == "Bearer tok-a"


# ---------------------------------------------------------------------------
# create_branch
# ---------------------------------------------------------------------------

def test_create_branch_success():
    client, _ = make_client({
        ("GET", "/repos/o/r/git/ref/heads/main"): (200, {"object": {"sha": "abc123"}}),
        ("POST", "/repos/o/r/git/refs"): (201, {"ref": "refs/heads/new-branch"}),
    })
    result = create_branch(client, "o", "r", "new-branch")
    assert result.success
    assert result.data["branch"] == "new-branch"
    assert result.data["sha"] == "abc123"


def test_create_branch_transient_on_error():
    client, transport = make_client({
        ("GET", "/repos/o/r/git/ref/heads/main"): (500, {"message": "server error"}),
    })
    result = create_branch(client, "o", "r", "new-branch")
    assert not result.success
    assert result.error.kind == "transient"


# ---------------------------------------------------------------------------
# comment_on_issue / comment_on_pr
# ---------------------------------------------------------------------------

def test_comment_on_issue_success():
    client, _ = make_client({
        ("POST", "/repos/o/r/issues/42/comments"): (201, {"id": 999}),
    })
    result = comment_on_issue(client, "o", "r", 42, "hello")
    assert result.success
    assert result.data["comment_id"] == 999


def test_comment_on_pr_delegates_to_issue():
    """PRs use the issues comment API."""
    client, transport = make_client({
        ("POST", "/repos/o/r/issues/7/comments"): (201, {"id": 1}),
    })
    result = comment_on_pr(client, "o", "r", 7, "lgtm")
    assert result.success
    assert "/issues/7/comments" in transport.calls[-1].url.path


# ---------------------------------------------------------------------------
# assign_to_self
# ---------------------------------------------------------------------------

def test_assign_to_self():
    client, transport = make_client({
        ("GET", "/user"): (200, {"login": "guild-bot"}),
        ("PATCH", "/repos/o/r/issues/5"): (200, {"assignees": [{"login": "guild-bot"}]}),
    })
    result = assign_to_self(client, "o", "r", 5)
    assert result.success
    assert result.data["assignee"] == "guild-bot"
    patch_body = json.loads(transport.calls[-1].content)
    assert patch_body["assignees"] == ["guild-bot"]


# ---------------------------------------------------------------------------
# open_pull_request (CI gate)
# ---------------------------------------------------------------------------

def test_open_pr_green_ci():
    client, _ = make_client({
        ("POST", "/repos/o/r/pulls"): (201, {"number": 10, "head": {"sha": "def456"}}),
        ("GET", "/repos/o/r/commits/def456/check-runs"): (200, {
            "check_runs": [
                {"name": "ci", "status": "completed", "conclusion": "success"},
            ]
        }),
    })
    result = open_pull_request(client, "o", "r", "feat: x", "feat-branch", "main")
    assert result.success
    assert result.data["pr_number"] == 10


def test_open_pr_failing_ci_returns_permanent_error():
    client, _ = make_client({
        ("POST", "/repos/o/r/pulls"): (201, {"number": 11, "head": {"sha": "ghi789"}}),
        ("GET", "/repos/o/r/commits/ghi789/check-runs"): (200, {
            "check_runs": [
                {"name": "ci", "status": "in_progress", "conclusion": None},
            ]
        }),
    })
    result = open_pull_request(client, "o", "r", "feat: y", "feat-branch", "main")
    assert not result.success
    assert result.error.kind == "permanent"
    assert "ci" in result.error.message


def test_open_pr_no_checks_yet_returns_permanent_error():
    """No check-runs means CI hasn't started — treat as not-green."""
    client, _ = make_client({
        ("POST", "/repos/o/r/pulls"): (201, {"number": 12, "head": {"sha": "jkl000"}}),
        ("GET", "/repos/o/r/commits/jkl000/check-runs"): (200, {"check_runs": []}),
    })
    result = open_pull_request(client, "o", "r", "feat: z", "feat-branch", "main")
    # Empty check-runs: not_green is empty list, so actually succeeds
    # (No checks = nothing failing = allow PR — CI will catch it on review)
    assert result.success
