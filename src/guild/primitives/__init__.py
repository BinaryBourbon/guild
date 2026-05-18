"""Action primitives: typed results + retry runner.

Design contract
---------------
* Every primitive returns ``ActionResult``.  It never raises (unless the
  error is a programming mistake, not a runtime failure).
* ``run_primitive`` retries transient errors with exponential back-off.
  On the *final* transient attempt it returns ``ActionResult(success=False)``
  instead of raising — callers always get a result they can act on.
* Permanent errors propagate immediately as a failed ``ActionResult``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class PrimitiveError(Exception):
    """Structured error from a primitive.

    kind:
        ``"transient"`` — may succeed on retry (network blip, rate-limit).
        ``"permanent"`` — will not succeed on retry (4xx, bad input).
    """

    kind: str  # "transient" | "permanent"
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    """Outcome of running a primitive.

    artifact: represents a record written to thread_artifacts (branch, PR,
    commit, comment), not arbitrary data.  None when no artifact was produced.
    """

    success: bool
    artifact: dict | None = None
    error: PrimitiveError | None = None


def run_primitive(
    fn: Callable[..., ActionResult],
    params: dict[str, Any],
    *,
    max_retries: int = 3,
    _sleep: Callable[[float], None] = time.sleep,  # injectable for tests
) -> ActionResult:
    """Execute *fn* with *params*, retrying transient failures.

    On the final transient attempt, returns a failed ``ActionResult`` instead
    of raising ``PrimitiveError`` — the caller always receives a typed result.
    """
    for attempt in range(max_retries):
        try:
            return fn(**params)
        except PrimitiveError as exc:
            if exc.kind == "transient":
                if attempt < max_retries - 1:
                    _sleep(2.0**attempt)
                    continue
                # Final attempt exhausted — return, do NOT raise
                return ActionResult(
                    success=False,
                    error=PrimitiveError("transient", "max retries exceeded", {"last_error": exc.message}),
                )
            if exc.kind == "permanent":
                return ActionResult(success=False, error=exc)
            raise  # programming error — unexpected kind
    # Should be unreachable, but satisfies type-checkers.
    return ActionResult(success=False, error=PrimitiveError("transient", "max retries exceeded"))  # pragma: no cover
