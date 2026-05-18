"""Work-management primitives: assignment, labels, status."""
from __future__ import annotations

import httpx

from guild.github_client import GitHubClient
from guild.primitives import ActionResult, PrimitiveError


def assign_to_self(
    client: GitHubClient,
    owner: str,
    repo: str,
    issue_number: int,
) -> ActionResult:
    """Assign *issue_number* to the authenticated user."""
    try:
        login = client.authenticated_user
        client.patch(
            f"/repos/{owner}/{repo}/issues/{issue_number}",
            json={"assignees": [login]},
        )
        return ActionResult(success=True, data={"assignee": login})
    except httpx.HTTPStatusError as exc:
        kind = "permanent" if 400 <= exc.response.status_code < 500 else "transient"
        return ActionResult(success=False, error=PrimitiveError(kind, str(exc)))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(success=False, error=PrimitiveError("transient", str(exc)))


def add_label(
    client: GitHubClient,
    owner: str,
    repo: str,
    issue_number: int,
    label: str,
) -> ActionResult:
    """Add *label* to *issue_number* (label must already exist in repo)."""
    try:
        client.post(
            f"/repos/{owner}/{repo}/issues/{issue_number}/labels",
            json={"labels": [label]},
        )
        return ActionResult(success=True, data={"label": label})
    except httpx.HTTPStatusError as exc:
        kind = "permanent" if 400 <= exc.response.status_code < 500 else "transient"
        return ActionResult(success=False, error=PrimitiveError(kind, str(exc)))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(success=False, error=PrimitiveError("transient", str(exc)))


def update_issue_status(
    client: GitHubClient,
    owner: str,
    repo: str,
    issue_number: int,
    state: str,
) -> ActionResult:
    """Set *issue_number* state to 'open' or 'closed'."""
    try:
        client.patch(
            f"/repos/{owner}/{repo}/issues/{issue_number}",
            json={"state": state},
        )
        return ActionResult(success=True, data={"state": state})
    except httpx.HTTPStatusError as exc:
        kind = "permanent" if 400 <= exc.response.status_code < 500 else "transient"
        return ActionResult(success=False, error=PrimitiveError(kind, str(exc)))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(success=False, error=PrimitiveError("transient", str(exc)))
