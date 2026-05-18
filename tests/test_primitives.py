"""Tests for GitHub API primitives using httpx mock transport."""
from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from guild.github_client import GitHubClient
from guild.primitives.code import create_branch, commit_and_push, open_pull_request, push_to_branch
from guild.primitives.communication import comment_on_issue, comment_on_pr
from guild.primitives.work import assign_to_self


class MockTransport(httpx.BaseTransport):
    """In-memory httpx transport backed by a response map.

    response_map keys are (method, path) tuples.
    Values are (status_code, json_body) tuples.

    A value may also be a list of (status_code, json_body) tuples to return
    different responses on successive calls to the same endpoint (consumed
    left-to-right; the last entry is repeated once exhausted).
    """

    def __init__(self, responses: dict) -> None:
        self._responses = responses
        self._call_counts: dict = {}
        self.calls: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        key = (request.method, request.url.path)
        if key not in self._responses:
            return httpx.Response(404, json={"message": f"not mocked: {key}"})
        entry = self._responses[key]
        # Support sequential responses: list of (status, body) tuples
        if isinstance(entry, list):
            idx = self._call_counts.get(key, 0)
            status, body = entry[min(idx, len(entry) - 1)]
            self._call_counts[key] = idx + 1
        else:
            status, body = entry
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
    assert result.artifact["branch"] == "new-branch"
    assert result.artifact["sha"] == "abc123"


def test_create_branch_permanent_on_4xx():
    """422 Reference Already Exists is a permanent error, not transient."""
    client, _ = make_client({
        ("GET", "/repos/o/r/git/ref/heads/main"): (200, {"object": {"sha": "abc"}}),
        ("POST", "/repos/o/r/git/refs"): (422, {"message": "Reference already exists"}),
    })
    result = create_branch(client, "o", "r", "existing-branch")
    assert not result.success
    assert result.error.kind == "permanent"


def test_create_branch_transient_on_5xx():
    client, _ = make_client({
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
    assert result.artifact["comment_id"] == 999


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
    assert result.artifact["assignee"] == "guild-bot"
    patch_body = json.loads(transport.calls[-1].content)
    assert patch_body["assignees"] == ["guild-bot"]


# ---------------------------------------------------------------------------
# open_pull_request — CI gate runs BEFORE PR creation (Fix 1)
# ---------------------------------------------------------------------------

def test_open_pr_green_ci():
    """Happy path: branch checks green → PR created."""
    client, transport = make_client({
        ("GET", "/repos/o/r/pulls"): (200, []),  # no existing PR
        ("GET", "/repos/o/r/git/ref/heads/feat-branch"): (200, {"object": {"sha": "def456"}}),
        ("GET", "/repos/o/r/commits/def456/check-runs"): (200, {
            "check_runs": [
                {"name": "ci", "status": "completed", "conclusion": "success"},
            ]
        }),
        ("POST", "/repos/o/r/pulls"): (201, {"number": 10, "head": {"sha": "def456"}}),
    })
    result = open_pull_request(client, "o", "r", "feat: x", "feat-branch", "main")
    assert result.success
    assert result.artifact["pr_number"] == 10
    assert result.artifact["head_sha"] == "def456"


def test_open_pr_reuses_existing_pr():
    """Idempotency: if an open PR exists, reuse it rather than creating a new one."""
    client, transport = make_client({
        ("GET", "/repos/o/r/pulls"): (200, [{"number": 99, "head": {"sha": "eee111"}}]),
        ("GET", "/repos/o/r/git/ref/heads/feat-branch"): (200, {"object": {"sha": "eee111"}}),
        ("GET", "/repos/o/r/commits/eee111/check-runs"): (200, {
            "check_runs": [{"name": "ci", "status": "completed", "conclusion": "success"}]
        }),
    })
    result = open_pull_request(client, "o", "r", "feat: x", "feat-branch", "main")
    assert result.success
    assert result.artifact["pr_number"] == 99
    # No POST to /pulls — existing PR was reused
    post_calls = [c for c in transport.calls if c.method == "POST"]
    assert len(post_calls) == 0


def test_open_pr_no_post_when_checks_failing():
    """Fix 1: POST /pulls must NOT be called when branch has failing checks."""
    client, transport = make_client({
        ("GET", "/repos/o/r/pulls"): (200, []),
        ("GET", "/repos/o/r/git/ref/heads/feat-branch"): (200, {"object": {"sha": "bad123"}}),
        ("GET", "/repos/o/r/commits/bad123/check-runs"): (200, {
            "check_runs": [
                {"name": "ci", "status": "completed", "conclusion": "failure"},
            ]
        }),
    })
    result = open_pull_request(client, "o", "r", "feat: y", "feat-branch", "main")
    assert not result.success
    assert result.error.kind == "permanent"
    assert "ci" in result.error.message
    # Critical assertion: no POST /pulls must have been made
    post_calls = [c for c in transport.calls if c.method == "POST"]
    assert len(post_calls) == 0, "POST /pulls must not be called on a failing branch"


def test_open_pr_failing_ci_in_progress_no_post():
    """In-progress check → permanent error, no POST /pulls."""
    client, transport = make_client({
        ("GET", "/repos/o/r/pulls"): (200, []),
        ("GET", "/repos/o/r/git/ref/heads/feat-branch"): (200, {"object": {"sha": "ghi789"}}),
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
    post_calls = [c for c in transport.calls if c.method == "POST"]
    assert len(post_calls) == 0, "POST /pulls must not be called while CI is running"


def test_open_pr_no_checks_yet_returns_transient_error():
    """Fix 3: Empty check-runs → transient (CI hasn't queued yet; retry will help)."""
    client, transport = make_client({
        ("GET", "/repos/o/r/pulls"): (200, []),
        ("GET", "/repos/o/r/git/ref/heads/feat-branch"): (200, {"object": {"sha": "jkl000"}}),
        ("GET", "/repos/o/r/commits/jkl000/check-runs"): (200, {"check_runs": []}),
    })
    result = open_pull_request(client, "o", "r", "feat: z", "feat-branch", "main")
    assert not result.success
    # Fix 3: must be transient — CI hasn't queued yet, retrying will find checks
    assert result.error.kind == "transient"
    assert "no check-runs" in result.error.message
    # No POST /pulls on a branch with no checks
    post_calls = [c for c in transport.calls if c.method == "POST"]
    assert len(post_calls) == 0


# ---------------------------------------------------------------------------
# commit_and_push / push_to_branch — six-step GitHub tree API (Fix 4)
# ---------------------------------------------------------------------------

_SIX_STEP_HAPPY = {
    ("GET", "/repos/o/r/git/ref/heads/feat"): (200, {"object": {"sha": "head111"}}),
    ("GET", "/repos/o/r/git/commits/head111"): (200, {"tree": {"sha": "tree000"}}),
    ("POST", "/repos/o/r/git/blobs"): (201, {"sha": "blob111"}),
    ("POST", "/repos/o/r/git/trees"): (201, {"sha": "newtree"}),
    ("POST", "/repos/o/r/git/commits"): (201, {"sha": "newcommit"}),
    ("PATCH", "/repos/o/r/git/refs/heads/feat"): (200, {"object": {"sha": "newcommit"}}),
}


def test_commit_and_push_happy_path():
    """All six steps succeed — returns artifact with new commit SHA."""
    client, transport = make_client(dict(_SIX_STEP_HAPPY))
    files = [{"path": "README.md", "content": "hello"}]
    result = commit_and_push(client, "o", "r", "feat", files, "add readme")
    assert result.success
    assert result.artifact["sha"] == "newcommit"
    # Verify all six API calls were made
    methods_paths = [(c.method, c.url.path) for c in transport.calls]
    assert ("GET", "/repos/o/r/git/ref/heads/feat") in methods_paths
    assert ("GET", "/repos/o/r/git/commits/head111") in methods_paths
    assert ("POST", "/repos/o/r/git/blobs") in methods_paths
    assert ("POST", "/repos/o/r/git/trees") in methods_paths
    assert ("POST", "/repos/o/r/git/commits") in methods_paths
    assert ("PATCH", "/repos/o/r/git/refs/heads/feat") in methods_paths


def test_push_to_branch_happy_path():
    """push_to_branch is an alias — same six-step happy path."""
    client, _ = make_client(dict(_SIX_STEP_HAPPY))
    files = [{"path": "src/foo.py", "content": "x = 1"}]
    result = push_to_branch(client, "o", "r", "feat", files, "fix: something")
    assert result.success
    assert result.artifact["sha"] == "newcommit"


def test_commit_and_push_transient_on_502_mid_sequence():
    """502 on create-blob (step 3) → transient error, sequence aborted."""
    responses = {
        ("GET", "/repos/o/r/git/ref/heads/feat"): (200, {"object": {"sha": "head111"}}),
        ("GET", "/repos/o/r/git/commits/head111"): (200, {"tree": {"sha": "tree000"}}),
        ("POST", "/repos/o/r/git/blobs"): (502, {"message": "bad gateway"}),
    }
    client, _ = make_client(responses)
    result = commit_and_push(client, "o", "r", "feat", [{"path": "f.py", "content": "x"}], "msg")
    assert not result.success
    assert result.error.kind == "transient"


def test_commit_and_push_permanent_on_403_update_ref():
    """403 on update-ref (step 6) → permanent error (auth / protected branch)."""
    responses = {
        ("GET", "/repos/o/r/git/ref/heads/feat"): (200, {"object": {"sha": "head111"}}),
        ("GET", "/repos/o/r/git/commits/head111"): (200, {"tree": {"sha": "tree000"}}),
        ("POST", "/repos/o/r/git/blobs"): (201, {"sha": "blob111"}),
        ("POST", "/repos/o/r/git/trees"): (201, {"sha": "newtree"}),
        ("POST", "/repos/o/r/git/commits"): (201, {"sha": "newcommit"}),
        ("PATCH", "/repos/o/r/git/refs/heads/feat"): (403, {"message": "protected branch"}),
    }
    client, _ = make_client(responses)
    result = commit_and_push(client, "o", "r", "feat", [{"path": "f.py", "content": "x"}], "msg")
    assert not result.success
    assert result.error.kind == "permanent"
