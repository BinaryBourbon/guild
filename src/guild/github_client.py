"""GitHub REST API client with swappable auth seam.

The TokenProvider callable allows PAT now and GitHub App tokens later
(which require JWT + installation token exchange) without changing callers.
"""
from __future__ import annotations

import functools
from typing import Any, Callable

import httpx

TokenProvider = Callable[[], str]


class GitHubClient:
    """Thin wrapper around the GitHub REST API.

    Args:
        token_provider: Zero-arg callable that returns the current bearer token.
            PAT usage: ``lambda: os.environ["GUILD_WORKER_GITHUB_TOKEN"]``.
            GitHub App usage: swap in a callable that fetches an installation token.
        http_client: Optional pre-built httpx.Client (for tests).  If omitted,
            a real client is created and owned by this instance.
        base_url: Override for testing against GitHub Enterprise or mocks.
    """

    def __init__(
        self,
        token_provider: TokenProvider,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = "https://api.github.com",
    ) -> None:
        self._token_provider = token_provider
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=self._base_url,
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            timeout=30.0,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token_provider()}"}

    @functools.cached_property
    def authenticated_user(self) -> str:
        """GitHub login of the authenticated user (cached after first call)."""
        data = self.get("/user")
        return data["login"]

    def get(self, path: str, **kwargs: Any) -> Any:
        """GET *path* and return parsed JSON.  Raises on non-2xx."""
        url = self._base_url + path if path.startswith("/") else path
        resp = self._client.get(url, headers=self._auth_headers(), **kwargs)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, json: Any, **kwargs: Any) -> Any:
        """POST *json* to *path* and return parsed JSON.  Raises on non-2xx."""
        url = self._base_url + path if path.startswith("/") else path
        resp = self._client.post(url, json=json, headers=self._auth_headers(), **kwargs)
        resp.raise_for_status()
        return resp.json()

    def patch(self, path: str, json: Any, **kwargs: Any) -> Any:
        """PATCH *json* to *path* and return parsed JSON.  Raises on non-2xx."""
        url = self._base_url + path if path.startswith("/") else path
        resp = self._client.patch(url, json=json, headers=self._auth_headers(), **kwargs)
        resp.raise_for_status()
        return resp.json()
