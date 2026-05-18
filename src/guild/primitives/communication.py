"""Communication primitives: issue and PR comments."""
from __future__ import annotations

import httpx

from guild.github_client import GitHubClient
from guild.primitives import ActionResult, PrimitiveError
from guild.primitives._utils import _http_error_kind


def comment_on_issue(
    client: GitHubClient,
    owner: str,
    repo: str,
    issue_number: int,
    body: str,
) -> ActionResult:
    """Post a comment on *issue_number*."""
    try:
        result = client.post(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json={"body": body},
        )
        return ActionResult(success=True, artifact={"comment_id": result["id"]})
    except httpx.HTTPStatusError as exc:
        return ActionResult(success=False, error=PrimitiveError(_http_error_kind(exc), str(exc)))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(success=False, error=PrimitiveError("transient", str(exc)))


def comment_on_pr(
    client: GitHubClient,
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
) -> ActionResult:
    """Post a comment on *pr_number* (PRs share the issues comment API)."""
    return comment_on_issue(client, owner, repo, pr_number, body)
