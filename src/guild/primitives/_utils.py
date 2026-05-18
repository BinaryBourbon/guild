"""Shared utilities for action primitives."""
from __future__ import annotations

import httpx


def _http_error_kind(exc: httpx.HTTPStatusError) -> str:
    """Map HTTP status to primitive error kind.

    4xx = permanent (bad request, auth, not-found — retrying won't help).
    5xx = transient (server error — may succeed on retry).
    """
    return "permanent" if 400 <= exc.response.status_code < 500 else "transient"
