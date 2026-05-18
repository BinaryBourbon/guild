"""Code primitives: branch, commit, PR.

open_pull_request gates on CI: it checks /check-runs after creating the PR
and returns PrimitiveError('permanent') if checks are not all green.
The polling loop will retry on the next cycle once CI finishes.

open_pull_request is idempotent: it checks for an existing open PR on the
same head/base before creating a new one. This prevents 422 errors when
the polling loop retries after a transient CI failure.
"""
from __future__ import annotations

import base64
from typing import Any

import httpx

from guild.github_client import GitHubClient
from guild.primitives import ActionResult, PrimitiveError


def _http_error_kind(exc: httpx.HTTPStatusError) -> str:
    """Map HTTP status to primitive error kind.

    4xx = permanent (bad request, auth, not-found — retrying won't help).
    5xx = transient (server error — may succeed on retry).
    """
    return "permanent" if 400 <= exc.response.status_code < 500 else "transient"


def create_branch(
    client: GitHubClient,
    owner: str,
    repo: str,
    branch: str,
    from_ref: str = "main",
) -> ActionResult:
    """Create *branch* off *from_ref* (default: main)."""
    try:
        ref_data = client.get(f"/repos/{owner}/{repo}/git/ref/heads/{from_ref}")
        sha = ref_data["object"]["sha"]
        client.post(
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )
        return ActionResult(success=True, data={"branch": branch, "sha": sha})
    except httpx.HTTPStatusError as exc:
        return ActionResult(success=False, error=PrimitiveError(_http_error_kind(exc), str(exc)))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(success=False, error=PrimitiveError("transient", str(exc)))


def _commit_files(
    client: GitHubClient,
    owner: str,
    repo: str,
    branch: str,
    files: list[dict[str, str]],
    message: str,
) -> dict[str, Any]:
    """Six-step GitHub API sequence to commit *files* to *branch*.

    files: list of {"path": str, "content": str} dicts.
    Returns the new commit object.
    """
    # 1. Get branch HEAD
    ref = client.get(f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
    head_sha = ref["object"]["sha"]

    # 2. Get current tree
    commit = client.get(f"/repos/{owner}/{repo}/git/commits/{head_sha}")
    base_tree_sha = commit["tree"]["sha"]

    # 3. Create blobs
    blobs = []
    for f in files:
        blob = client.post(
            f"/repos/{owner}/{repo}/git/blobs",
            json={"content": base64.b64encode(f["content"].encode()).decode(), "encoding": "base64"},
        )
        blobs.append({"path": f["path"], "mode": "100644", "type": "blob", "sha": blob["sha"]})

    # 4. Create tree
    tree = client.post(
        f"/repos/{owner}/{repo}/git/trees",
        json={"base_tree": base_tree_sha, "tree": blobs},
    )

    # 5. Create commit
    new_commit = client.post(
        f"/repos/{owner}/{repo}/git/commits",
        json={"message": message, "tree": tree["sha"], "parents": [head_sha]},
    )

    # 6. Update ref
    client.patch(
        f"/repos/{owner}/{repo}/git/refs/heads/{branch}",
        json={"sha": new_commit["sha"]},
    )
    return new_commit


def commit_and_push(
    client: GitHubClient,
    owner: str,
    repo: str,
    branch: str,
    files: list[dict[str, str]],
    message: str,
) -> ActionResult:
    """Commit *files* to *branch* using the six-step GitHub API sequence."""
    try:
        commit = _commit_files(client, owner, repo, branch, files, message)
        return ActionResult(success=True, data={"sha": commit["sha"]})
    except httpx.HTTPStatusError as exc:
        return ActionResult(success=False, error=PrimitiveError(_http_error_kind(exc), str(exc)))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(success=False, error=PrimitiveError("transient", str(exc)))


def push_to_branch(
    client: GitHubClient,
    owner: str,
    repo: str,
    branch: str,
    files: list[dict[str, str]],
    message: str,
) -> ActionResult:
    """Alias for commit_and_push (clearer name at call sites)."""
    return commit_and_push(client, owner, repo, branch, files, message)


def open_pull_request(
    client: GitHubClient,
    owner: str,
    repo: str,
    title: str,
    head: str,
    base: str,
    body: str = "",
) -> ActionResult:
    """Open a PR (idempotent) and verify CI checks are green.

    Checks for an existing open PR first to avoid duplicate creation on retry.
    If checks are not all green, returns PrimitiveError('permanent') so the
    polling loop retries next cycle once CI has had time to complete.
    Empty check-runs (CI not yet queued) is also treated as not-green.
    """
    try:
        # Idempotency: check for an existing open PR before creating
        existing = client.get(
            f"/repos/{owner}/{repo}/pulls",
            params={"head": f"{owner}:{head}", "base": base, "state": "open"},
        )
        if existing:
            pr = existing[0]
        else:
            pr = client.post(
                f"/repos/{owner}/{repo}/pulls",
                json={"title": title, "head": head, "base": base, "body": body},
            )
        pr_number = pr["number"]
        head_sha = pr["head"]["sha"]
    except httpx.HTTPStatusError as exc:
        return ActionResult(success=False, error=PrimitiveError(_http_error_kind(exc), str(exc)))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(success=False, error=PrimitiveError("transient", str(exc)))

    # Gate: verify CI checks are all green
    try:
        checks = client.get(f"/repos/{owner}/{repo}/commits/{head_sha}/check-runs")
        runs = checks.get("check_runs", [])
        if not runs:
            # No checks queued yet — CI hasn't started; treat as not-green
            return ActionResult(
                success=False,
                error=PrimitiveError("permanent", "no check-runs found; CI may not have started yet", {"pr_number": pr_number}),
            )
        not_green = [
            r for r in runs
            if r.get("status") != "completed" or r.get("conclusion") not in ("success", "skipped", "neutral")
        ]
        if not_green:
            names = [r.get("name", "?") for r in not_green]
            return ActionResult(
                success=False,
                error=PrimitiveError(
                    "permanent",
                    f"CI checks not green: {names}",
                    {"pr_number": pr_number, "failing_checks": names},
                ),
            )
    except httpx.HTTPStatusError as exc:
        return ActionResult(success=False, error=PrimitiveError(_http_error_kind(exc), str(exc)))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(success=False, error=PrimitiveError("transient", str(exc)))

    return ActionResult(success=True, data={"pr_number": pr_number, "head_sha": head_sha})
