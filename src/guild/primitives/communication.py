"""Communication primitives: issue and PR comments."""
from __future__ import annotations

from guild.github_client import GitHubClient
from guild.primitives import ActionResult, PrimitiveError


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
        return ActionResult(success=True, data={"comment_id": result["id"]})
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
