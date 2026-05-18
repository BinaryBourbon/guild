"""Code primitives: branch, commit, PR.

open_pull_request gates on CI before creating the PR:
1. Check for an existing open PR (idempotency — reuse it and re-verify CI).
2. Resolve branch HEAD SHA via GET /git/ref/heads/{branch}.
3. Poll check-runs on that SHA.
4. If no checks yet: return PrimitiveError('transient') — CI hasn't queued yet,
   retry later.  This is transient because the situation resolves itself once
   the CI runner picks up the push.
5. If checks are red: return PrimitiveError('permanent') — the worker must fix
   the failure before retrying.
6. Only if checks are all green: POST /pulls to create the PR.

This ordering guarantees a PR is never opened on a failing or unverified
branch, per docs/05 Verification Requirement and engineering-plan §3.
"""
from __future__ import annotations

import base64
from typing import Any

import httpx

from guild.github_client import GitHubClient
from guild.primitives import ActionResult, PrimitiveError
from guild.primitives._utils import _http_error_kind


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
        return ActionResult(success=True, artifact={"branch": branch, "sha": sha})
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
        return ActionResult(success=True, artifact={"sha": commit["sha"]})
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
    """Open a PR (idempotent) — CI gate runs BEFORE PR creation.

    Ordering enforced:
    1. Look up any existing open PR — reuse it if found (idempotency).
    2. Resolve branch HEAD SHA via GET /git/ref/heads/{head}.
    3. Poll check-runs on that SHA.
    4. No checks yet → PrimitiveError('transient'): CI hasn't queued, retry later.
    5. Any check not green → PrimitiveError('permanent'): fix the code first.
    6. All green → POST /pulls (or return existing PR).
    """
    try:
        # Step 1: idempotency — check for an existing open PR
        existing = client.get(
            f"/repos/{owner}/{repo}/pulls",
            params={"head": f"{owner}:{head}", "base": base, "state": "open"},
        )
        existing_pr = existing[0] if existing else None

        # Step 2: resolve branch HEAD SHA from the ref (authoritative, independent
        # of whether a PR exists yet)
        ref = client.get(f"/repos/{owner}/{repo}/git/ref/heads/{head}")
        head_sha = ref["object"]["sha"]
    except httpx.HTTPStatusError as exc:
        return ActionResult(success=False, error=PrimitiveError(_http_error_kind(exc), str(exc)))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(success=False, error=PrimitiveError("transient", str(exc)))

    # Step 3: gate on CI check-runs BEFORE touching /pulls
    try:
        checks = client.get(f"/repos/{owner}/{repo}/commits/{head_sha}/check-runs")
        runs = checks.get("check_runs", [])

        if not runs:
            # No checks queued yet — CI hasn't started on this branch.
            # This is TRANSIENT: the CI runner will pick up the push shortly;
            # retrying after a delay will find checks queued.
            return ActionResult(
                success=False,
                error=PrimitiveError(
                    "transient",
                    "[transient] no check-runs yet: CI has not started on this branch; retry later",
                ),
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
                    {"failing_checks": names},
                ),
            )
    except httpx.HTTPStatusError as exc:
        return ActionResult(success=False, error=PrimitiveError(_http_error_kind(exc), str(exc)))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(success=False, error=PrimitiveError("transient", str(exc)))

    # Step 4 (step 6 in docstring): all checks green — create or reuse the PR
    try:
        if existing_pr is not None:
            pr = existing_pr
        else:
            pr = client.post(
                f"/repos/{owner}/{repo}/pulls",
                json={"title": title, "head": head, "base": base, "body": body},
            )
        pr_number = pr["number"]
    except httpx.HTTPStatusError as exc:
        return ActionResult(success=False, error=PrimitiveError(_http_error_kind(exc), str(exc)))
    except Exception as exc:  # noqa: BLE001
        return ActionResult(success=False, error=PrimitiveError("transient", str(exc)))

    return ActionResult(success=True, artifact={"pr_number": pr_number, "head_sha": head_sha})
